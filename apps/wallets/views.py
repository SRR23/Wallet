"""
Wallet balance and transaction history.

Requires tenant-user JWT + matching X-Tenant-ID.
"""
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.models import LedgerEntry
from apps.ledger.serializers import LedgerEntrySerializer
from apps.tenants.authentication import TENANT_HEADER, TenantUserJWTAuthentication
from apps.wallets.models import Wallet
from apps.wallets.serializers import WalletSerializer

TENANT_HEADER_REQUIRED = OpenApiParameter(
    name=TENANT_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "Required tenant UUID. Must match the tenant_id claim in the tenant-user access token."
    ),
)

PAGE_PARAMETER = OpenApiParameter(
    name="page",
    type=int,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Page number (default 1). Response includes count, next, previous, results.",
)


class WalletTransactionPagination(PageNumberPagination):
    """Standard DRF page links: count / next / previous / results."""

    page_size = 20
    page_size_query_param = None
    max_page_size = 20


class MyWalletView(APIView):
    """GET the authenticated user's wallet balance."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["wallets"],
        summary="Get my wallet balance",
        description=(
            "Returns the wallet that belongs to the authenticated tenant user "
            "(created automatically at register).\n\n"
            "`balance` is an integer in **minor units** (paisa for BDT). "
            "Example: `1000` means 10.00 BDT.\n\n"
            "**Auth:** tenant-user Bearer JWT + matching `X-Tenant-ID`.\n\n"
            "Prefer this over `/api/wallets/{wallet_id}/` when you do not need to pass the id."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        responses={200: WalletSerializer},
    )
    def get(self, request):
        wallet = request.tenant_user.wallet
        return Response(WalletSerializer(wallet).data)


class WalletDetailView(APIView):
    """GET a wallet by id if it belongs to the current tenant user."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["wallets"],
        summary="Get wallet by id",
        description=(
            "Returns a wallet by UUID **only if it belongs to the authenticated user** "
            "in the current tenant.\n\n"
            "Another user's wallet id → **404** (no cross-user reads).\n\n"
            "**Auth:** tenant-user Bearer JWT + matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        responses={200: WalletSerializer},
    )
    def get(self, request, wallet_id):
        wallet = get_object_or_404(
            Wallet,
            id=wallet_id,
            tenant=request.tenant,
            user=request.tenant_user,
        )
        return Response(WalletSerializer(wallet).data)


class WalletTransactionListView(APIView):
    """Paginated ledger history for the authenticated user's wallet."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = WalletTransactionPagination

    @extend_schema(
        tags=["wallets"],
        summary="List wallet transaction history",
        description=(
            "Returns **immutable ledger entries** for a wallet (the full money history).\n\n"
            "- `GET /api/wallets/me/transactions/` — history for the logged-in user's wallet\n"
            "- `GET /api/wallets/{wallet_id}/transactions/` — same, but wallet id must be yours\n\n"
            "Each entry has `entry_type` (`DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, "
            "`TRANSFER_OUT`), `amount` (minor units), and `balance_after`.\n\n"
            "Paginated (DRF standard): `count`, `next`, `previous`, `results`. "
            "Use query `?page=2` to follow `next`.\n\n"
            "**Auth:** tenant-user Bearer JWT + matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED, PAGE_PARAMETER],
        responses={200: LedgerEntrySerializer(many=True)},
    )
    def get(self, request, wallet_id=None):
        if wallet_id is None:
            wallet = request.tenant_user.wallet
        else:
            wallet = get_object_or_404(
                Wallet,
                id=wallet_id,
                tenant=request.tenant,
                user=request.tenant_user,
            )

        entries = LedgerEntry.objects.filter(
            wallet=wallet,
            tenant=request.tenant,
        ).select_related("transaction")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(entries, request, view=self)
        serializer = LedgerEntrySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
