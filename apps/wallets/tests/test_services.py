"""
Wallet creation tests.
"""
import pytest

from apps.tenants.services import create_user
from apps.wallets.models import Wallet


@pytest.mark.django_db
def test_create_user_opens_wallet(tenant):
    user = create_user(
        tenant=tenant,
        email="bob@example.com",
        name="Bob",
        password="strong-pass-123",
    )

    wallet = Wallet.objects.get(user=user)
    assert wallet.tenant_id == tenant.id
    assert wallet.balance == 0
    assert wallet.currency == "BDT"
    assert user.wallet.id == wallet.id
