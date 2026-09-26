"""
Custom DRF permissions.
"""
from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    """Only Django users with is_superuser=True (platform admin JWT)."""

    message = "Only a super admin can access this resource."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_superuser", False)
        )


class IsTenantUser(BasePermission):
    """Require a tenant-scoped JWT principal (TenantUserPrincipal)."""

    message = "Tenant user authentication is required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request, "tenant_user")
        )
