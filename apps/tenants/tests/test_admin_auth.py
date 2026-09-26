"""Platform admin login tests (views live in apps.tenants)."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status

AuthUser = get_user_model()


@pytest.mark.django_db
def test_admin_login_success(api_client):
    AuthUser.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin-pass-123",
    )
    response = api_client.post(
        "/api/auth/admin/login/",
        {"username": "admin", "password": "admin-pass-123"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert response.data["user"]["is_superuser"] is True
