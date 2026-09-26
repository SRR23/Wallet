"""
Create and look up tenants and tenant-scoped users.

User registration also opens a zero-balance wallet in the same transaction.
"""
from django.db import transaction

from apps.tenants.models import Tenant, User


def create_tenant(*, name: str) -> Tenant:
    """Create a tenant. The returned id is what clients send as X-Tenant-ID."""
    return Tenant.objects.create(name=name)


@transaction.atomic
def create_user(
    *,
    tenant: Tenant,
    email: str,
    name: str,
    password: str,
) -> User:
    """
    Register a user under the given tenant and auto-create their wallet.

    Both rows commit together or neither does.
    """
    from apps.wallets.services import create_wallet

    user = User(
        tenant=tenant,
        email=email,
        name=name,
    )
    user.set_password(password)
    user.save()
    create_wallet(user=user, currency="BDT")
    return user


def update_user(*, user: User, name: str | None = None) -> User:
    """Update mutable profile fields for the authenticated tenant user."""
    if name is not None:
        user.name = name
    user.save(update_fields=["name", "updated_at"])
    return user
