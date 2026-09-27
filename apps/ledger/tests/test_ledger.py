"""
Ledger and wallet money-flow tests (assessment core cases).
"""
import threading

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.ledger.models import LedgerEntry, LedgerTransaction
from apps.ledger.services import deposit, transfer, withdraw
from apps.tenants.models import Tenant
from apps.tenants.services import create_user
from apps.tenants.tokens import issue_tenant_user_tokens
from apps.wallets.models import Wallet


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="OtherCo")


@pytest.fixture
def user_a(tenant):
    return create_user(
        tenant=tenant,
        email="a@example.com",
        name="A",
        password="strong-pass-123",
    )


@pytest.fixture
def user_b(tenant):
    return create_user(
        tenant=tenant,
        email="b@example.com",
        name="B",
        password="strong-pass-123",
    )


@pytest.fixture
def other_user(other_tenant):
    return create_user(
        tenant=other_tenant,
        email="x@example.com",
        name="X",
        password="strong-pass-123",
    )


def _auth_client(user):
    client = APIClient()
    tokens = issue_tenant_user_tokens(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.defaults["HTTP_X_TENANT_ID"] = str(user.tenant_id)
    return client


@pytest.mark.django_db
def test_deposit_and_balance(user_a):
    result = deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=5000,
        idempotency_key="dep-1",
    )
    assert result.replayed is False
    user_a.wallet.refresh_from_db()
    assert user_a.wallet.balance == 5000
    assert LedgerEntry.objects.filter(wallet=user_a.wallet).count() == 1


@pytest.mark.django_db
def test_withdraw_insufficient_funds(user_a):
    deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=100,
        idempotency_key="dep-2",
    )
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError) as exc:
        withdraw(
            tenant=user_a.tenant,
            wallet=user_a.wallet,
            amount=500,
            idempotency_key="wd-1",
        )
    assert "Insufficient funds" in str(exc.value.detail)
    user_a.wallet.refresh_from_db()
    assert user_a.wallet.balance == 100


@pytest.mark.django_db
def test_idempotent_deposit(user_a):
    first = deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=1000,
        idempotency_key="same-key",
    )
    second = deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=1000,
        idempotency_key="same-key",
    )
    assert first.replayed is False
    assert second.replayed is True
    assert first.transaction.id == second.transaction.id
    user_a.wallet.refresh_from_db()
    assert user_a.wallet.balance == 1000
    assert LedgerTransaction.objects.filter(idempotency_key="same-key").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_idempotency_key_deposit(user_a):
    """Two overlapping deposits with the same key must credit once only."""
    results = []
    errors = []

    def do_deposit():
        try:
            results.append(
                deposit(
                    tenant=user_a.tenant,
                    wallet=Wallet.objects.get(pk=user_a.wallet.id),
                    amount=1000,
                    idempotency_key="race-same-key",
                )
            )
        except Exception as exc:  # noqa: BLE001 — collect either outcome
            errors.append(exc)

    t1 = threading.Thread(target=do_deposit)
    t2 = threading.Thread(target=do_deposit)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    assert len(results) == 2
    assert sum(1 for r in results if r.replayed) == 1
    assert sum(1 for r in results if not r.replayed) == 1
    assert results[0].transaction.id == results[1].transaction.id

    user_a.wallet.refresh_from_db()
    assert user_a.wallet.balance == 1000
    assert (
        LedgerTransaction.objects.filter(
            tenant=user_a.tenant,
            idempotency_key="race-same-key",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_idempotency_rejects_amount_mismatch(user_a):
    deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=1000,
        idempotency_key="amt-key",
    )
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError) as exc:
        deposit(
            tenant=user_a.tenant,
            wallet=user_a.wallet,
            amount=2000,
            idempotency_key="amt-key",
        )
    assert "different amount" in str(exc.value.detail).lower()
    user_a.wallet.refresh_from_db()
    assert user_a.wallet.balance == 1000


@pytest.mark.django_db
def test_idempotency_rejects_wallet_mismatch(user_a, user_b):
    deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=500,
        idempotency_key="wal-key",
    )
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError) as exc:
        deposit(
            tenant=user_a.tenant,
            wallet=user_b.wallet,
            amount=500,
            idempotency_key="wal-key",
        )
    assert "destination wallet" in str(exc.value.detail).lower()
    user_a.wallet.refresh_from_db()
    user_b.wallet.refresh_from_db()
    assert user_a.wallet.balance == 500
    assert user_b.wallet.balance == 0


@pytest.mark.django_db
def test_transfer_same_tenant(user_a, user_b):
    deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=1000,
        idempotency_key="dep-tr",
    )
    result = transfer(
        tenant=user_a.tenant,
        from_wallet=user_a.wallet,
        to_wallet=user_b.wallet,
        amount=400,
        idempotency_key="tr-1",
    )
    assert result.replayed is False
    user_a.wallet.refresh_from_db()
    user_b.wallet.refresh_from_db()
    assert user_a.wallet.balance == 600
    assert user_b.wallet.balance == 400
    assert result.transaction.entries.count() == 2


@pytest.mark.django_db
def test_cross_tenant_transfer_blocked(user_a, other_user):
    deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=1000,
        idempotency_key="dep-x",
    )
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        transfer(
            tenant=user_a.tenant,
            from_wallet=user_a.wallet,
            to_wallet=other_user.wallet,
            amount=100,
            idempotency_key="tr-x",
        )
    user_a.wallet.refresh_from_db()
    other_user.wallet.refresh_from_db()
    assert user_a.wallet.balance == 1000
    assert other_user.wallet.balance == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_transfers(user_a, user_b):
    deposit(
        tenant=user_a.tenant,
        wallet=user_a.wallet,
        amount=1000,
        idempotency_key="dep-conc",
    )

    errors = []

    def do_transfer(key_suffix: str):
        try:
            transfer(
                tenant=user_a.tenant,
                from_wallet=Wallet.objects.get(pk=user_a.wallet.id),
                to_wallet=Wallet.objects.get(pk=user_b.wallet.id),
                amount=600,
                idempotency_key=f"conc-{key_suffix}",
            )
        except Exception as exc:  # noqa: BLE001 — collect either outcome
            errors.append(exc)

    t1 = threading.Thread(target=do_transfer, args=("1",))
    t2 = threading.Thread(target=do_transfer, args=("2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    user_a.wallet.refresh_from_db()
    user_b.wallet.refresh_from_db()
    # Only one 600 transfer can succeed from 1000; the other must fail.
    assert user_a.wallet.balance + user_b.wallet.balance == 1000
    assert user_a.wallet.balance in (400, 1000)
    assert len(errors) == 1


@pytest.mark.django_db
def test_api_deposit_withdraw_transfer_and_history(user_a, user_b):
    client = _auth_client(user_a)

    dep = client.post(
        "/api/ledger/deposit/",
        {"amount": 2000, "idempotency_key": "api-dep-1"},
        format="json",
    )
    assert dep.status_code == status.HTTP_201_CREATED
    assert dep.data["replayed"] is False

    bal = client.get("/api/wallets/me/")
    assert bal.status_code == status.HTTP_200_OK
    assert bal.data["balance"] == 2000

    wd = client.post(
        "/api/ledger/withdraw/",
        {"amount": 500, "idempotency_key": "api-wd-1"},
        format="json",
    )
    assert wd.status_code == status.HTTP_201_CREATED

    tr = client.post(
        "/api/ledger/transfer/",
        {
            "to_wallet_id": str(user_b.wallet.id),
            "amount": 300,
            "idempotency_key": "api-tr-1",
        },
        format="json",
    )
    assert tr.status_code == status.HTTP_201_CREATED
    # Both entries returned; counterparty balance_after is stripped.
    entries_by_wallet = {str(e["wallet"]): e for e in tr.data["entries"]}
    mine = entries_by_wallet[str(user_a.wallet.id)]
    theirs = entries_by_wallet[str(user_b.wallet.id)]
    assert "balance_after" in mine
    assert mine["balance_after"] == 1200  # 2000 - 500 withdraw - 300 transfer
    assert "balance_after" not in theirs

    # Idempotent replay
    tr2 = client.post(
        "/api/ledger/transfer/",
        {
            "to_wallet_id": str(user_b.wallet.id),
            "amount": 300,
            "idempotency_key": "api-tr-1",
        },
        format="json",
    )
    assert tr2.status_code == status.HTTP_200_OK
    assert tr2.data["replayed"] is True
    assert tr2.data["id"] == tr.data["id"]

    history = client.get("/api/wallets/me/transactions/")
    assert history.status_code == status.HTTP_200_OK
    assert history.data["count"] >= 3
    assert "results" in history.data
    assert "next" in history.data
    assert "previous" in history.data
    assert "page" not in history.data
    assert "page_size" not in history.data

    # Cross-tenant destination rejected at API validation
    other = create_user(
        tenant=Tenant.objects.create(name="Z"),
        email="z@example.com",
        name="Z",
        password="strong-pass-123",
    )
    bad = client.post(
        "/api/ledger/transfer/",
        {
            "to_wallet_id": str(other.wallet.id),
            "amount": 10,
            "idempotency_key": "api-tr-bad",
        },
        format="json",
    )
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
