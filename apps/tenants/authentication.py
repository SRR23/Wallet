"""
Tenant header resolution and tenant-user JWT authentication.
"""
from rest_framework import authentication, exceptions
from rest_framework_simplejwt.exceptions import InvalidToken

from apps.tenants.models import Tenant, User
from apps.tenants.tokens import decode_tenant_user_access_token

TENANT_HEADER = "X-Tenant-ID"


class TenantUserPrincipal:
    """
    DRF-compatible principal for a logged-in tenants.User.

    is_superuser is always False — platform admin uses Django auth JWT.
    """

    def __init__(self, user: User):
        self.tenant_user = user
        self.id = user.id
        self.pk = user.pk
        self.email = user.email
        self.name = user.name
        self.tenant_id = user.tenant_id

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_superuser(self) -> bool:
        return False

    @property
    def is_staff(self) -> bool:
        return False

    def __str__(self) -> str:
        return self.email


def _resolve_tenant(tenant_id: str) -> Tenant:
    try:
        return Tenant.objects.get(pk=tenant_id.strip())
    except (Tenant.DoesNotExist, ValueError, TypeError):
        raise exceptions.AuthenticationFailed("Invalid or unknown tenant.")


class TenantHeaderAuthentication(authentication.BaseAuthentication):
    """Optional X-Tenant-ID → request.tenant. Never owns request.user."""

    def authenticate(self, request):
        tenant_id = request.headers.get(TENANT_HEADER)
        if not tenant_id:
            return None
        request.tenant = _resolve_tenant(tenant_id)
        return None

    def authenticate_header(self, request):
        return TENANT_HEADER


class RequiredTenantHeaderAuthentication(authentication.BaseAuthentication):
    """Require valid X-Tenant-ID → request.tenant."""

    def authenticate(self, request):
        tenant_id = request.headers.get(TENANT_HEADER)
        if not tenant_id:
            raise exceptions.AuthenticationFailed(
                f"{TENANT_HEADER} header is required."
            )
        request.tenant = _resolve_tenant(tenant_id)
        return None

    def authenticate_header(self, request):
        return TENANT_HEADER


class TenantUserJWTAuthentication(authentication.BaseAuthentication):
    """
    Authenticate a tenants.User from Bearer JWT and require matching X-Tenant-ID.

    Sets request.tenant and request.tenant_user.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        try:
            token = decode_tenant_user_access_token(parts[1])
        except InvalidToken as exc:
            raise exceptions.AuthenticationFailed(str(exc.detail if hasattr(exc, "detail") else exc)) from exc

        header_tenant_id = request.headers.get(TENANT_HEADER)
        if not header_tenant_id:
            raise exceptions.AuthenticationFailed(
                f"{TENANT_HEADER} header is required."
            )

        token_tenant_id = str(token["tenant_id"])
        if header_tenant_id.strip() != token_tenant_id:
            raise exceptions.AuthenticationFailed(
                f"{TENANT_HEADER} does not match the authenticated user tenant."
            )

        try:
            user = User.objects.select_related("tenant").get(pk=token["user_id"])
        except (User.DoesNotExist, ValueError, TypeError):
            raise exceptions.AuthenticationFailed("User not found.")

        if str(user.tenant_id) != token_tenant_id:
            raise exceptions.AuthenticationFailed("Token tenant mismatch.")

        request.tenant = user.tenant
        request.tenant_user = user
        return (TenantUserPrincipal(user), token)

    def authenticate_header(self, request):
        return self.keyword
