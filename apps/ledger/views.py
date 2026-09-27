"""
Ledger API views: deposit, withdraw, transfer.

Authenticated tenant user operates on their own wallet (source).
Requires JWT + matching X-Tenant-ID.
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.serializers import (
    LedgerTransactionSerializer,
    MoneyMutationSerializer,
    TransferSerializer,
)
from apps.ledger.services import deposit, transfer, withdraw
from apps.tenants.authentication import TENANT_HEADER, TenantUserJWTAuthentication

TENANT_HEADER_REQUIRED = OpenApiParameter(
    name=TENANT_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "Required tenant UUID. Must match the tenant_id claim in the tenant-user access token."
    ),
)


def _transaction_response(result, *, viewer_wallet_id=None) -> Response:
    status_code = (
        status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED
    )
    context = {}
    if viewer_wallet_id is not None:
        context["viewer_wallet_id"] = viewer_wallet_id
    payload = LedgerTransactionSerializer(
        result.transaction,
        context=context,
    ).data
    payload["replayed"] = result.replayed
    return Response(payload, status=status_code)


class DepositView(APIView):
    """Deposit into the authenticated user's wallet."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["ledger"],
        summary="Deposit funds into my wallet",
        description=(
            "Credits the **authenticated user's wallet**.\n\n"
            "**Body:**\n"
            "- `amount` — positive integer in **minor units** (paisa). Example: `1000` = 10.00 BDT\n"
            "- `idempotency_key` — client-generated string, unique per tenant. "
            "Retries with the same key return the original result and never double-credit "
            "(`replayed: true`, HTTP 200).\n\n"
            "Creates an immutable ledger entry of type `DEPOSIT` and updates wallet balance "
            "in the same database transaction.\n\n"
            "**Auth:** tenant-user Bearer JWT + matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=MoneyMutationSerializer,
        responses={201: LedgerTransactionSerializer},
    )
    def post(self, request):
        serializer = MoneyMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = deposit(
            tenant=request.tenant,
            wallet=request.tenant_user.wallet,
            amount=serializer.validated_data["amount"],
            idempotency_key=serializer.validated_data["idempotency_key"],
        )
        return _transaction_response(result)


class WithdrawView(APIView):
    """Withdraw from the authenticated user's wallet."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["ledger"],
        summary="Withdraw funds from my wallet",
        description=(
            "Debits the **authenticated user's wallet**.\n\n"
            "**Body:** `amount` (minor units) and `idempotency_key` "
            "(unique per tenant; safe to retry).\n\n"
            "If balance is too low → **400** with `Insufficient funds` "
            "(no ledger row is written).\n\n"
            "On success, creates a `WITHDRAWAL` ledger entry and updates balance atomically.\n\n"
            "**Auth:** tenant-user Bearer JWT + matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=MoneyMutationSerializer,
        responses={201: LedgerTransactionSerializer},
    )
    def post(self, request):
        serializer = MoneyMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = withdraw(
            tenant=request.tenant,
            wallet=request.tenant_user.wallet,
            amount=serializer.validated_data["amount"],
            idempotency_key=serializer.validated_data["idempotency_key"],
        )
        return _transaction_response(result)


class TransferView(APIView):
    """Transfer from the authenticated user's wallet to another wallet in the tenant."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["ledger"],
        summary="Transfer funds to another wallet (same tenant)",
        description=(
            "Moves money **from the authenticated user's wallet** to another wallet "
            "in the **same tenant**.\n\n"
            "**Body:**\n"
            "- `to_wallet_id` — destination wallet UUID (must exist in this tenant)\n"
            "- `amount` — positive integer in minor units\n"
            "- `idempotency_key` — unique per tenant; retries are safe\n\n"
            "Writes two ledger entries in one atomic transaction "
            "(`TRANSFER_OUT` + `TRANSFER_IN`) with `select_for_update` locking.\n\n"
            "Both entries are returned, but `balance_after` is omitted on the "
            "**other** wallet’s entry (privacy).\n\n"
            "Cross-tenant destinations are rejected. Insufficient funds → **400**.\n\n"
            "**Auth:** tenant-user Bearer JWT + matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=TransferSerializer,
        responses={201: LedgerTransactionSerializer},
    )
    def post(self, request):
        serializer = TransferSerializer(
            data=request.data,
            context={"tenant": request.tenant},
        )
        serializer.is_valid(raise_exception=True)
        my_wallet = request.tenant_user.wallet
        result = transfer(
            tenant=request.tenant,
            from_wallet=my_wallet,
            to_wallet=serializer.context["to_wallet"],
            amount=serializer.validated_data["amount"],
            idempotency_key=serializer.validated_data["idempotency_key"],
        )
        return _transaction_response(result, viewer_wallet_id=my_wallet.id)
