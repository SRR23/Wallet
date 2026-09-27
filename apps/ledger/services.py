"""
Ledger money-movement services.

All balance changes go through these functions with:
- transaction.atomic()
- select_for_update() on wallets (ordered by id to avoid deadlocks)
- claim idempotency key *before* mutating balance (savepoint-safe race path)
- per-tenant idempotency_key uniqueness, matching amount + wallets on replay
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

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


def _wallet_ids_equal(left, right) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return left == right


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


def _assert_idempotent_payload_matches(
    existing: LedgerTransaction,
    *,
    expected_operation: str,
    amount: int,
    wallet_from_id: UUID | None,
    wallet_to_id: UUID | None,
) -> None:
    """
    Same key must mean the same logical request.

    Mismatched operation, amount, or wallets is treated as a client error —
    never silently replay a different transfer.
    """
    if existing.operation != expected_operation:
        raise ValidationError(
            {"idempotency_key": "Key already used for a different operation."}
        )
    if existing.amount != amount:
        raise ValidationError(
            {
                "idempotency_key": (
                    "Key already used with a different amount. "
                    "Reuse the original amount or choose a new key."
                )
            }
        )
    if not _wallet_ids_equal(existing.wallet_from_id, wallet_from_id):
        raise ValidationError(
            {
                "idempotency_key": (
                    "Key already used with a different source wallet."
                )
            }
        )
    if not _wallet_ids_equal(existing.wallet_to_id, wallet_to_id):
        raise ValidationError(
            {
                "idempotency_key": (
                    "Key already used with a different destination wallet."
                )
            }
        )


def _replay_or_none(
    *,
    tenant: Tenant,
    key: str,
    expected_operation: str,
    amount: int,
    wallet_from_id: UUID | None,
    wallet_to_id: UUID | None,
) -> LedgerResult | None:
    existing = _get_existing_transaction(tenant=tenant, idempotency_key=key)
    if existing is None:
        return None
    _assert_idempotent_payload_matches(
        existing,
        expected_operation=expected_operation,
        amount=amount,
        wallet_from_id=wallet_from_id,
        wallet_to_id=wallet_to_id,
    )
    return LedgerResult(transaction=existing, replayed=True)


def _claim_transaction(
    *,
    tenant: Tenant,
    operation: str,
    key: str,
    amount: int,
    wallet_from: Wallet | None,
    wallet_to: Wallet | None,
) -> LedgerTransaction | LedgerResult:
    """
    Insert the ledger transaction row to claim the idempotency key.

    Uses a savepoint so a concurrent unique violation does not abort the
    outer atomic block. Balance is updated only after a successful claim.
    """
    try:
        with transaction.atomic():
            return LedgerTransaction.objects.create(
                tenant=tenant,
                operation=operation,
                idempotency_key=key,
                amount=amount,
                wallet_from=wallet_from,
                wallet_to=wallet_to,
            )
    except IntegrityError:
        replay = _replay_or_none(
            tenant=tenant,
            key=key,
            expected_operation=operation,
            amount=amount,
            wallet_from_id=wallet_from.id if wallet_from else None,
            wallet_to_id=wallet_to.id if wallet_to else None,
        )
        if replay is not None:
            return replay
        raise


@transaction.atomic
def deposit(
    *,
    tenant: Tenant,
    wallet: Wallet,
    amount: int,
    idempotency_key: str,
) -> LedgerResult:
    """Credit a wallet. Idempotent per tenant + key (same amount + wallet)."""
    _validate_amount(amount)
    key = _validate_idempotency_key(idempotency_key)

    if wallet.tenant_id != tenant.id:
        raise ValidationError("Wallet does not belong to this tenant.")

    replay_kwargs = {
        "tenant": tenant,
        "key": key,
        "expected_operation": OPERATION_DEPOSIT,
        "amount": amount,
        "wallet_from_id": None,
        "wallet_to_id": wallet.id,
    }

    early = _replay_or_none(**replay_kwargs)
    if early is not None:
        return early

    (locked_wallet,) = _lock_wallets(wallet)

    after_lock = _replay_or_none(**{**replay_kwargs, "wallet_to_id": locked_wallet.id})
    if after_lock is not None:
        return after_lock

    claimed = _claim_transaction(
        tenant=tenant,
        operation=OPERATION_DEPOSIT,
        key=key,
        amount=amount,
        wallet_from=None,
        wallet_to=locked_wallet,
    )
    if isinstance(claimed, LedgerResult):
        return claimed
    tx = claimed

    locked_wallet.balance = F("balance") + amount
    locked_wallet.save(update_fields=["balance", "updated_at"])
    locked_wallet.refresh_from_db(fields=["balance"])

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

    replay_kwargs = {
        "tenant": tenant,
        "key": key,
        "expected_operation": OPERATION_WITHDRAW,
        "amount": amount,
        "wallet_from_id": wallet.id,
        "wallet_to_id": None,
    }

    early = _replay_or_none(**replay_kwargs)
    if early is not None:
        return early

    (locked_wallet,) = _lock_wallets(wallet)

    after_lock = _replay_or_none(
        **{**replay_kwargs, "wallet_from_id": locked_wallet.id}
    )
    if after_lock is not None:
        return after_lock

    if locked_wallet.balance < amount:
        raise ValidationError({"amount": "Insufficient funds."})

    claimed = _claim_transaction(
        tenant=tenant,
        operation=OPERATION_WITHDRAW,
        key=key,
        amount=amount,
        wallet_from=locked_wallet,
        wallet_to=None,
    )
    if isinstance(claimed, LedgerResult):
        return claimed
    tx = claimed

    locked_wallet.balance = F("balance") - amount
    locked_wallet.save(update_fields=["balance", "updated_at"])
    locked_wallet.refresh_from_db(fields=["balance"])

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

    Both sides succeed or neither does. Idempotent per tenant + key
    (same amount + both wallets).
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

    replay_kwargs = {
        "tenant": tenant,
        "key": key,
        "expected_operation": OPERATION_TRANSFER,
        "amount": amount,
        "wallet_from_id": from_wallet.id,
        "wallet_to_id": to_wallet.id,
    }

    early = _replay_or_none(**replay_kwargs)
    if early is not None:
        return early

    locked_from, locked_to = _lock_wallets(from_wallet, to_wallet)

    after_lock = _replay_or_none(
        **{
            **replay_kwargs,
            "wallet_from_id": locked_from.id,
            "wallet_to_id": locked_to.id,
        }
    )
    if after_lock is not None:
        return after_lock

    if locked_from.balance < amount:
        raise ValidationError({"amount": "Insufficient funds."})

    claimed = _claim_transaction(
        tenant=tenant,
        operation=OPERATION_TRANSFER,
        key=key,
        amount=amount,
        wallet_from=locked_from,
        wallet_to=locked_to,
    )
    if isinstance(claimed, LedgerResult):
        return claimed
    tx = claimed

    locked_from.balance = F("balance") - amount
    locked_to.balance = F("balance") + amount
    locked_from.save(update_fields=["balance", "updated_at"])
    locked_to.save(update_fields=["balance", "updated_at"])
    locked_from.refresh_from_db(fields=["balance"])
    locked_to.refresh_from_db(fields=["balance"])

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
