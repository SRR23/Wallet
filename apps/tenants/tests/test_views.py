"""
Tests for tenant-scoped auth and super-admin gating.

Requires local Postgres (see conftest.py).
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant, User
from apps.tenants.services import create_user
from apps.tenants.tokens import issue_tenant_user_tokens

AuthUser = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def tenant_user(tenant):
    return create_user(
        tenant=tenant,
        email="ada@example.com",
        name="Ada",
        password="strong-pass-123",
    )


@pytest.fixture
def superuser(db):
    return AuthUser.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin-pass-123",
    )


@pytest.fixture
def normal_django_user(db):
    return AuthUser.objects.create_user(
        username="member",
        email="member@example.com",
        password="member-pass-123",
    )


@pytest.fixture
def superuser_client(superuser):
    """Authenticated client for a Django superuser. Own client instance."""
    client = APIClient()
    token = RefreshToken.for_user(superuser).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def normal_django_client(normal_django_user):
    """Authenticated client for a non-superuser Django user. Own client instance."""
    client = APIClient()
    token = RefreshToken.for_user(normal_django_user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def tenant_auth_client(tenant, tenant_user):
    """Authenticated tenant-user client. Own client instance."""
    client = APIClient()
    tokens = issue_tenant_user_tokens(tenant_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


@pytest.mark.django_db
def test_create_tenant(api_client):
    response = api_client.post("/api/tenants/", {"name": "Acme"}, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert Tenant.objects.filter(id=response.data["id"]).exists()


@pytest.mark.django_db
def test_register_requires_tenant_header(api_client):
    response = api_client.post(
        "/api/auth/register/",
        {
            "email": "a@example.com",
            "name": "Ada",
            "password": "strong-pass-123",
            "password_confirm": "strong-pass-123",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["error"] == "authentication_failed"


@pytest.mark.django_db
def test_register_login_refresh_me(api_client, tenant):
    register = api_client.post(
        "/api/auth/register/",
        {
            "email": "Ada@Example.com",
            "name": "Ada",
            "password": "strong-pass-123",
            "password_confirm": "strong-pass-123",
        },
        format="json",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert register.status_code == status.HTTP_201_CREATED
    assert register.data["user"]["email"] == "ada@example.com"
    assert "access" in register.data
    assert "wallet" in register.data
    assert register.data["wallet"]["balance"] == 0
    assert register.data["wallet"]["currency"] == "BDT"
    # DRF may return UUID fields as UUID instances; compare as strings.
    assert str(register.data["wallet"]["user"]) == str(register.data["user"]["id"])
    assert str(register.data["wallet"]["tenant"]) == str(tenant.id)

    login = api_client.post(
        "/api/auth/login/",
        {"email": "ada@example.com", "password": "strong-pass-123"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert login.status_code == status.HTTP_200_OK
    access = login.data["access"]
    refresh = login.data["refresh"]

    me = api_client.get(
        "/api/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert me.status_code == status.HTTP_200_OK
    assert me.data["name"] == "Ada"

    patched = api_client.patch(
        "/api/auth/me/",
        {"name": "Ada Lovelace"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.data["name"] == "Ada Lovelace"

    refreshed = api_client.post(
        "/api/auth/refresh/",
        {"refresh": refresh},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert refreshed.status_code == status.HTTP_200_OK
    assert "access" in refreshed.data


@pytest.mark.django_db
def test_me_rejects_mismatched_tenant_header(api_client, tenant, tenant_user):
    other = Tenant.objects.create(name="Other")
    tokens = issue_tenant_user_tokens(tenant_user)

    response = api_client.get(
        "/api/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        HTTP_X_TENANT_ID=str(other.id),
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_login_wrong_tenant_fails(api_client, tenant, tenant_user):
    other = Tenant.objects.create(name="Other")
    response = api_client.post(
        "/api/auth/login/",
        {"email": "ada@example.com", "password": "strong-pass-123"},
        format="json",
        HTTP_X_TENANT_ID=str(other.id),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_list_tenants_requires_superuser(api_client, normal_django_client, superuser_client):
    Tenant.objects.create(name="Acme")

    # api_client stays anonymous — auth fixtures use separate APIClient instances.
    assert api_client.get("/api/tenants/").status_code == status.HTTP_401_UNAUTHORIZED
    assert normal_django_client.get("/api/tenants/").status_code == status.HTTP_403_FORBIDDEN

    ok = superuser_client.get("/api/tenants/")
    assert ok.status_code == status.HTTP_200_OK
    assert len(ok.data) == 1


@pytest.mark.django_db
def test_admin_login_rejects_non_superuser(api_client, normal_django_user):
    response = api_client.post(
        "/api/auth/admin/login/",
        {"username": "member", "password": "member-pass-123"},
        format="json",
    )
    # Admin login has authentication_classes = [], so DRF maps AuthenticationFailed → 403.
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"] == "permission_denied"


@pytest.mark.django_db
def test_admin_login_and_list_users(api_client, superuser, tenant, tenant_user):
    login = api_client.post(
        "/api/auth/admin/login/",
        {"username": "admin", "password": "admin-pass-123"},
        format="json",
    )
    assert login.status_code == status.HTTP_200_OK

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    users = api_client.get("/api/tenants/users/")
    assert users.status_code == status.HTTP_200_OK
    assert len(users.data) == 1
