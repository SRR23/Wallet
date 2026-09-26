"""
Wallet model.

One wallet per tenants.User. Balance is stored in integer minor units
(paisa for BDT). The ledger remains the source of truth for money movement;
update balance only inside the same DB transaction as a ledger entry.
"""
import uuid

from django.db import models

from apps.tenants.models import Tenant, User


class Wallet(models.Model):
    """Tenant-scoped wallet owned by exactly one domain user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="wallets",
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    # Minor units (e.g. paisa). Never use float.
    balance = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="BDT")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name="wallet_balance_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Wallet {self.id} ({self.user_id})"
