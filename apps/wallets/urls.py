from django.urls import path

from apps.wallets.views import MyWalletView, WalletDetailView, WalletTransactionListView

app_name = "wallets"

urlpatterns = [
    path("me/", MyWalletView.as_view(), name="my-wallet"),
    path("me/transactions/", WalletTransactionListView.as_view(), name="my-transactions"),
    path("<uuid:wallet_id>/", WalletDetailView.as_view(), name="wallet-detail"),
    path(
        "<uuid:wallet_id>/transactions/",
        WalletTransactionListView.as_view(),
        name="wallet-transactions",
    ),
]
