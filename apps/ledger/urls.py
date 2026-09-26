from django.urls import path

from apps.ledger.views import DepositView, TransferView, WithdrawView

app_name = "ledger"

urlpatterns = [
    path("deposit/", DepositView.as_view(), name="deposit"),
    path("withdraw/", WithdrawView.as_view(), name="withdraw"),
    path("transfer/", TransferView.as_view(), name="transfer"),
]
