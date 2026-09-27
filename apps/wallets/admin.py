from django.contrib import admin

from apps.wallets.models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """
    Inspection only. Balance must change only via ledger services —
    never through Django admin edits.
    """

    list_display = ("id", "tenant", "user", "balance", "currency", "created_at")
    list_filter = ("currency", "tenant")
    search_fields = ("id", "user__email")
    readonly_fields = (
        "id",
        "tenant",
        "user",
        "balance",
        "currency",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Allow opening the change form for inspection; all fields are read-only.
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Belt-and-suspenders: never persist admin edits to wallet rows.
        return
