"""Wallet API serializers."""
from rest_framework import serializers

from apps.wallets.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    balance = serializers.IntegerField(
        read_only=True,
        help_text="Current balance in minor units (paisa). 1000 = 10.00 BDT.",
    )
    currency = serializers.CharField(
        read_only=True,
        help_text="ISO-style currency code. Wallets are created as BDT.",
    )

    class Meta:
        model = Wallet
        fields = (
            "id",
            "tenant",
            "user",
            "balance",
            "currency",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
