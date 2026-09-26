"""
Immutable ledger models.

LedgerTransaction = one logical money operation (idempotent per tenant).
LedgerEntry = one wallet-side posting; never updated or deleted after create.
"""
import uuid

from django.db import models

from apps.tenants.models import Tenant
from apps.wallets.models import Wallet
from utils.constants import LEDGER_ENTRY_TYPE_CHOICES, LEDGER_OPERATION_CHOICES


class LedgerTransaction(models.Model):
    """
    Logical deposit / withdraw / transfer.

    Unique (tenant, idempotency_key) so retries never double-post.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="ledger_transactions",
    )
    operation = models.CharField(max_length=20, choices=LEDGER_OPERATION_CHOICES)
    idempotency_key = models.CharField(max_length=128)
    amount = models.BigIntegerField(
        help_text="Positive amount in minor units for this operation.",
    )
    # Wallets involved (transfer uses both; deposit/withdraw use wallet_from only).
    wallet_from = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="outgoing_transactions",
        null=True,
        blank=True,
    )
    wallet_to = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="incoming_transactions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_tenant_idempotency_key",
            ),
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="ledger_tx_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.operation} {self.amount} ({self.idempotency_key})"


class LedgerEntry(models.Model):
    """Immutable posting against a single wallet."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    transaction = models.ForeignKey(
        LedgerTransaction,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    entry_type = models.CharField(max_length=20, choices=LEDGER_ENTRY_TYPE_CHOICES)
    # Always positive; credit/debit is encoded in entry_type.
    amount = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="ledger_entry_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount} on {self.wallet_id}"
