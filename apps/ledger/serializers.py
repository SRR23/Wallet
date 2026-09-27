"""Serializers for ledger deposit / withdraw / transfer / history."""
from rest_framework import serializers

from apps.ledger.models import LedgerEntry, LedgerTransaction
from apps.wallets.models import Wallet


class LedgerEntrySerializer(serializers.ModelSerializer):
    entry_type = serializers.CharField(
        read_only=True,
        help_text="debit or credit relative to this wallet.",
    )
    amount = serializers.IntegerField(
        read_only=True,
        help_text="Absolute amount in minor units (paisa).",
    )
    balance_after = serializers.IntegerField(
        read_only=True,
        help_text="Wallet balance after this entry was applied.",
    )

    class Meta:
        model = LedgerEntry
        fields = (
            "id",
            "wallet",
            "entry_type",
            "amount",
            "balance_after",
            "transaction",
            "created_at",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Transfer API may pass viewer_wallet_id to hide the other party's balance.
        viewer_wallet_id = self.context.get("viewer_wallet_id")
        if viewer_wallet_id is not None and str(instance.wallet_id) != str(
            viewer_wallet_id
        ):
            data.pop("balance_after", None)
        return data


class LedgerTransactionSerializer(serializers.ModelSerializer):
    entries = LedgerEntrySerializer(many=True, read_only=True)
    operation = serializers.CharField(
        read_only=True,
        help_text="deposit, withdraw, or transfer.",
    )
    amount = serializers.IntegerField(
        read_only=True,
        help_text="Transaction amount in minor units (paisa).",
    )

    class Meta:
        model = LedgerTransaction
        fields = (
            "id",
            "operation",
            "idempotency_key",
            "amount",
            "wallet_from",
            "wallet_to",
            "entries",
            "created_at",
        )
        read_only_fields = fields


class MoneyMutationSerializer(serializers.Serializer):
    amount = serializers.IntegerField(
        min_value=1,
        help_text="Positive amount in minor units (paisa). Example: 1000 = 10.00 BDT.",
    )
    idempotency_key = serializers.CharField(
        max_length=128,
        help_text="Client-generated key, unique per tenant. Safe to retry with the same key.",
    )


class TransferSerializer(serializers.Serializer):
    to_wallet_id = serializers.UUIDField(
        help_text="Destination wallet UUID. Must belong to the same tenant.",
    )
    amount = serializers.IntegerField(
        min_value=1,
        help_text="Positive amount in minor units (paisa).",
    )
    idempotency_key = serializers.CharField(
        max_length=128,
        help_text="Client-generated key, unique per tenant. Safe to retry with the same key.",
    )

    def validate_to_wallet_id(self, value):
        tenant = self.context["tenant"]
        try:
            wallet = Wallet.objects.get(id=value, tenant=tenant)
        except Wallet.DoesNotExist:
            raise serializers.ValidationError(
                "Destination wallet not found in this tenant."
            )
        self.context["to_wallet"] = wallet
        return value
