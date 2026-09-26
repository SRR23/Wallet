from django.contrib import admin

from apps.tenants.models import Tenant, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "name", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("email", "name")
    readonly_fields = ("id", "password", "created_at", "updated_at")
