"""
JWT helpers for tenant-scoped users (apps.tenants.models.User).

Tokens are separate from Django AUTH_USER_MODEL JWTs used by super admin.
Claims include user_id, tenant_id, and principal=tenant_user.

Refresh tokens rotate and are blacklisted. OutstandingToken.user stays null
because AUTH_USER_MODEL is the platform Django user, not tenants.User —
simplejwt's built-in outstand/blacklist would try to load a UUID as an int PK.
"""
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from apps.tenants.models import User

PRINCIPAL_TENANT_USER = "tenant_user"
PRINCIPAL_CLAIM = "principal"


class TenantUserAccessToken(AccessToken):
    pass


class TenantUserRefreshToken(RefreshToken):
    access_token_class = TenantUserAccessToken

    @classmethod
    def for_tenant_user(cls, user) -> "TenantUserRefreshToken":
        token = cls()
        token[PRINCIPAL_CLAIM] = PRINCIPAL_TENANT_USER
        token["user_id"] = str(user.id)
        token["tenant_id"] = str(user.tenant_id)
        token["email"] = user.email

        access = token.access_token
        access[PRINCIPAL_CLAIM] = PRINCIPAL_TENANT_USER
        access["user_id"] = str(user.id)
        access["tenant_id"] = str(user.tenant_id)
        access["email"] = user.email

        _outstand_tenant_refresh(token)
        return token


def _outstand_tenant_refresh(token: TenantUserRefreshToken) -> OutstandingToken:
    """Record refresh jti without resolving AUTH_USER_MODEL."""
    jti = token[api_settings.JTI_CLAIM]
    outstanding, _ = OutstandingToken.objects.get_or_create(
        jti=jti,
        defaults={
            "user": None,
            "created_at": token.current_time,
            "token": str(token),
            "expires_at": datetime_from_epoch(token["exp"]),
        },
    )
    return outstanding


def _blacklist_tenant_refresh(token: TenantUserRefreshToken) -> None:
    """Blacklist by jti. Raises InvalidToken if already blacklisted."""
    jti = token.payload[api_settings.JTI_CLAIM]
    if BlacklistedToken.objects.filter(token__jti=jti).exists():
        raise InvalidToken("Token is blacklisted")

    outstanding = _outstand_tenant_refresh(token)
    BlacklistedToken.objects.get_or_create(token=outstanding)


def issue_tenant_user_tokens(user) -> dict:
    refresh = TenantUserRefreshToken.for_tenant_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def decode_tenant_user_access_token(raw_token: str) -> TenantUserAccessToken:
    try:
        token = TenantUserAccessToken(raw_token)
    except TokenError as exc:
        raise InvalidToken(str(exc)) from exc

    if token.get(PRINCIPAL_CLAIM) != PRINCIPAL_TENANT_USER:
        raise InvalidToken("Not a tenant-user token.")
    return token


def refresh_tenant_user_tokens(raw_refresh: str) -> dict:
    """
    Rotate refresh: blacklist the presented token and issue a new pair.

    Reusing the old refresh after this call must fail (blacklisted).
    """
    try:
        refresh = TenantUserRefreshToken(raw_refresh)
    except TokenError as exc:
        raise InvalidToken(str(exc)) from exc

    if refresh.get(PRINCIPAL_CLAIM) != PRINCIPAL_TENANT_USER:
        raise InvalidToken("Not a tenant-user refresh token.")

    try:
        user = User.objects.get(pk=refresh["user_id"])
    except User.DoesNotExist as exc:
        raise InvalidToken("User not found.") from exc

    if str(user.tenant_id) != str(refresh["tenant_id"]):
        raise InvalidToken("Token tenant mismatch.")

    _blacklist_tenant_refresh(refresh)
    return issue_tenant_user_tokens(user)


def blacklist_tenant_user_refresh(raw_refresh: str) -> None:
    """Invalidate a refresh token (logout). Access tokens expire naturally."""
    try:
        refresh = TenantUserRefreshToken(raw_refresh)
    except TokenError as exc:
        raise InvalidToken(str(exc)) from exc

    if refresh.get(PRINCIPAL_CLAIM) != PRINCIPAL_TENANT_USER:
        raise InvalidToken("Not a tenant-user refresh token.")

    _blacklist_tenant_refresh(refresh)
