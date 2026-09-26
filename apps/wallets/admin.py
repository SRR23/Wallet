from django.contrib import admin

from apps.wallets.models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "user", "balance", "currency", "created_at")
    list_filter = ("currency", "tenant")
    search_fields = ("id", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
