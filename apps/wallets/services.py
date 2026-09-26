"""
Wallet services.

Opening a wallet belongs here. Deposit / withdraw / transfer stay in ledger.
"""
from apps.tenants.models import User
from apps.wallets.models import Wallet


def create_wallet(*, user: User, currency: str = "BDT") -> Wallet:
    """
    Open a zero-balance wallet for a tenant user.

    Caller should already be inside transaction.atomic() when registering.
    """
    return Wallet.objects.create(
        tenant=user.tenant,
        user=user,
        balance=0,
        currency=currency,
    )
