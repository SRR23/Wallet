"""
Ledger money-movement services.

All balance changes go through these functions with:
- transaction.atomic()
- select_for_update() on wallets (ordered by id to avoid deadlocks)
- per-tenant idempotency_key uniqueness
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework.exceptions import NotFound, ValidationError

from apps.ledger.models import LedgerEntry, LedgerTransaction
from apps.tenants.models import Tenant
from apps.wallets.models import Wallet
from utils.constants import (
    ENTRY_DEPOSIT,
    ENTRY_TRANSFER_IN,
    ENTRY_TRANSFER_OUT,
    ENTRY_WITHDRAWAL,
    OPERATION_DEPOSIT,
    OPERATION_TRANSFER,
    OPERATION_WITHDRAW,
)


@dataclass(frozen=True)
class LedgerResult:
    """Return value for deposit / withdraw / transfer (including idempotent replays)."""

    transaction: LedgerTransaction
    replayed: bool


def _get_existing_transaction(
    *,
    tenant: Tenant,
    idempotency_key: str,
) -> LedgerTransaction | None:
    return (
        LedgerTransaction.objects.filter(
            tenant=tenant,
            idempotency_key=idempotency_key,
        )
        .prefetch_related("entries")
        .first()
    )


def _lock_wallets(*wallets: Wallet) -> list[Wallet]:
    """
    Lock wallet rows in deterministic id order to prevent deadlocks.
    Returns wallets in the same order as the arguments.
    """
    ids = [wallet.id for wallet in wallets]
    locked = {
        wallet.id: wallet
        for wallet in Wallet.objects.select_for_update()
        .filter(id__in=ids)
        .order_by("id")
    }
    missing = [wallet_id for wallet_id in ids if wallet_id not in locked]
    if missing:
        raise NotFound("Wallet not found.")
    return [locked[wallet_id] for wallet_id in ids]


def _validate_amount(amount: int) -> None:
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValidationError({"amount": "Amount must be an integer in minor units."})
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})


def _validate_idempotency_key(idempotency_key: str) -> str:
    key = (idempotency_key or "").strip()
    if not key:
        raise ValidationError({"idempotency_key": "This field is required."})
    if len(key) > 128:
        raise ValidationError({"idempotency_key": "Must be at most 128 characters."})
    return key


def _replay_or_none(
    *,
    tenant: Tenant,
    key: str,
    expected_operation: str,
) -> LedgerResult | None:
    existing = _get_existing_transaction(tenant=tenant, idempotency_key=key)
    if existing is None:
        return None
    if existing.operation != expected_operation:
        raise ValidationError(
            {"idempotency_key": "Key already used for a different operation."}
        )
    return LedgerResult(transaction=existing, replayed=True)


@transaction.atomic
def deposit(
    *,
    tenant: Tenant,
    wallet: Wallet,
    amount: int,
    idempotency_key: str,
) -> LedgerResult:
    """Credit a wallet. Idempotent per tenant + key."""
    _validate_amount(amount)
    key = _validate_idempotency_key(idempotency_key)

    if wallet.tenant_id != tenant.id:
        raise ValidationError("Wallet does not belong to this tenant.")

    early = _replay_or_none(tenant=tenant, key=key, expected_operation=OPERATION_DEPOSIT)
    if early is not None:
        return early

    (locked_wallet,) = _lock_wallets(wallet)

    # Re-check after lock so concurrent retries never double-credit.
    after_lock = _replay_or_none(
        tenant=tenant, key=key, expected_operation=OPERATION_DEPOSIT
    )
    if after_lock is not None:
        return after_lock

    locked_wallet.balance = F("balance") + amount
    locked_wallet.save(update_fields=["balance", "updated_at"])
    locked_wallet.refresh_from_db(fields=["balance"])

    try:
        tx = LedgerTransaction.objects.create(
            tenant=tenant,
            operation=OPERATION_DEPOSIT,
            idempotency_key=key,
            amount=amount,
            wallet_to=locked_wallet,
        )
    except IntegrityError:
        replay = _replay_or_none(
            tenant=tenant, key=key, expected_operation=OPERATION_DEPOSIT
        )
        if replay is not None:
            return replay
        raise

    LedgerEntry.objects.create(
        tenant=tenant,
        transaction=tx,
        wallet=locked_wallet,
        entry_type=ENTRY_DEPOSIT,
        amount=amount,
        balance_after=locked_wallet.balance,
    )
    tx = LedgerTransaction.objects.prefetch_related("entries").get(pk=tx.pk)
    return LedgerResult(transaction=tx, replayed=False)


@transaction.atomic
def withdraw(
    *,
    tenant: Tenant,
    wallet: Wallet,
    amount: int,
    idempotency_key: str,
) -> LedgerResult:
    """Debit a wallet. Rejects insufficient funds. Idempotent per tenant + key."""
    _validate_amount(amount)
    key = _validate_idempotency_key(idempotency_key)

    if wallet.tenant_id != tenant.id:
        raise ValidationError("Wallet does not belong to this tenant.")

    early = _replay_or_none(tenant=tenant, key=key, expected_operation=OPERATION_WITHDRAW)
    if early is not None:
        return early

    (locked_wallet,) = _lock_wallets(wallet)

    after_lock = _replay_or_none(
        tenant=tenant, key=key, expected_operation=OPERATION_WITHDRAW
    )
    if after_lock is not None:
        return after_lock

    if locked_wallet.balance < amount:
        raise ValidationError({"amount": "Insufficient funds."})

    locked_wallet.balance = F("balance") - amount
    locked_wallet.save(update_fields=["balance", "updated_at"])
    locked_wallet.refresh_from_db(fields=["balance"])

    try:
        tx = LedgerTransaction.objects.create(
            tenant=tenant,
            operation=OPERATION_WITHDRAW,
            idempotency_key=key,
            amount=amount,
            wallet_from=locked_wallet,
        )
    except IntegrityError:
        replay = _replay_or_none(
            tenant=tenant, key=key, expected_operation=OPERATION_WITHDRAW
        )
        if replay is not None:
            return replay
        raise

    LedgerEntry.objects.create(
        tenant=tenant,
        transaction=tx,
        wallet=locked_wallet,
        entry_type=ENTRY_WITHDRAWAL,
        amount=amount,
        balance_after=locked_wallet.balance,
    )
    tx = LedgerTransaction.objects.prefetch_related("entries").get(pk=tx.pk)
    return LedgerResult(transaction=tx, replayed=False)


@transaction.atomic
def transfer(
    *,
    tenant: Tenant,
    from_wallet: Wallet,
    to_wallet: Wallet,
    amount: int,
    idempotency_key: str,
) -> LedgerResult:
    """
    Move funds between two wallets of the same tenant.

    Both sides succeed or neither does. Idempotent per tenant + key.
    """
    _validate_amount(amount)
    key = _validate_idempotency_key(idempotency_key)

    if from_wallet.id == to_wallet.id:
        raise ValidationError("Cannot transfer to the same wallet.")

    if from_wallet.tenant_id != tenant.id or to_wallet.tenant_id != tenant.id:
        raise ValidationError("Cross-tenant transfers are not allowed.")

    if from_wallet.tenant_id != to_wallet.tenant_id:
        raise ValidationError("Cross-tenant transfers are not allowed.")

    if from_wallet.currency != to_wallet.currency:
        raise ValidationError("Wallets must use the same currency.")

    early = _replay_or_none(tenant=tenant, key=key, expected_operation=OPERATION_TRANSFER)
    if early is not None:
        return early

    locked_from, locked_to = _lock_wallets(from_wallet, to_wallet)

    after_lock = _replay_or_none(
        tenant=tenant, key=key, expected_operation=OPERATION_TRANSFER
    )
    if after_lock is not None:
        return after_lock

    if locked_from.balance < amount:
        raise ValidationError({"amount": "Insufficient funds."})

    locked_from.balance = F("balance") - amount
    locked_to.balance = F("balance") + amount
    locked_from.save(update_fields=["balance", "updated_at"])
    locked_to.save(update_fields=["balance", "updated_at"])
    locked_from.refresh_from_db(fields=["balance"])
    locked_to.refresh_from_db(fields=["balance"])

    try:
        tx = LedgerTransaction.objects.create(
            tenant=tenant,
            operation=OPERATION_TRANSFER,
            idempotency_key=key,
            amount=amount,
            wallet_from=locked_from,
            wallet_to=locked_to,
        )
    except IntegrityError:
        replay = _replay_or_none(
            tenant=tenant, key=key, expected_operation=OPERATION_TRANSFER
        )
        if replay is not None:
            return replay
        raise

    LedgerEntry.objects.create(
        tenant=tenant,
        transaction=tx,
        wallet=locked_from,
        entry_type=ENTRY_TRANSFER_OUT,
        amount=amount,
        balance_after=locked_from.balance,
    )
    LedgerEntry.objects.create(
        tenant=tenant,
        transaction=tx,
        wallet=locked_to,
        entry_type=ENTRY_TRANSFER_IN,
        amount=amount,
        balance_after=locked_to.balance,
    )
    tx = LedgerTransaction.objects.prefetch_related("entries").get(pk=tx.pk)
    return LedgerResult(transaction=tx, replayed=False)
