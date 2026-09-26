"""
JWT helpers for tenant-scoped users (apps.tenants.models.User).

Tokens are separate from Django AUTH_USER_MODEL JWTs used by super admin.
Claims include user_id, tenant_id, and principal=tenant_user.
"""
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

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
        return token


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
    try:
        refresh = TenantUserRefreshToken(raw_refresh)
    except TokenError as exc:
        raise InvalidToken(str(exc)) from exc

    if refresh.get(PRINCIPAL_CLAIM) != PRINCIPAL_TENANT_USER:
        raise InvalidToken("Not a tenant-user refresh token.")

    access = refresh.access_token
    access[PRINCIPAL_CLAIM] = PRINCIPAL_TENANT_USER
    access["user_id"] = refresh["user_id"]
    access["tenant_id"] = refresh["tenant_id"]
    access["email"] = refresh.get("email", "")

    return {
        "access": str(access),
        "refresh": str(refresh),
    }
