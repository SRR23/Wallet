from django.contrib import admin

from apps.ledger.models import LedgerEntry, LedgerTransaction


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    readonly_fields = (
        "id",
        "wallet",
        "entry_type",
        "amount",
        "balance_after",
        "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "operation",
        "amount",
        "tenant",
        "idempotency_key",
        "created_at",
    )
    list_filter = ("operation", "tenant")
    search_fields = ("idempotency_key", "id")
    readonly_fields = (
        "id",
        "tenant",
        "operation",
        "idempotency_key",
        "amount",
        "wallet_from",
        "wallet_to",
        "created_at",
    )
    inlines = [LedgerEntryInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entry_type",
        "amount",
        "balance_after",
        "wallet",
        "tenant",
        "created_at",
    )
    list_filter = ("entry_type", "tenant")
    search_fields = ("id", "wallet__id")
    readonly_fields = (
        "id",
        "tenant",
        "transaction",
        "wallet",
        "entry_type",
        "amount",
        "balance_after",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
