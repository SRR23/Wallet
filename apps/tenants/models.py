"""
Tenant and tenant-scoped user models.

X-Tenant-ID identifies the Tenant row. Users always belong to exactly one
tenant. Email uniqueness is per tenant, not global.

This User authenticates with tenant-scoped JWT (register/login). It is not
Django's AUTH_USER_MODEL — platform super admin stays django.contrib.auth.
"""
import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class Tenant(models.Model):
    """Organization or merchant that owns users and wallets."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(models.Model):
    """
    Account and wallet owner under a single tenant.

    Register / login / refresh / me are scoped by X-Tenant-ID.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="users",
    )
    email = models.EmailField()
    name = models.CharField(max_length=255)
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "email"],
                name="uniq_tenant_user_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.tenant_id})"

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)
