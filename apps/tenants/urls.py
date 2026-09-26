"""
All tenant and auth URL routes (mounted under /api/).
"""
from django.conf import settings
from django.urls import path

from apps.tenants.views import (
    AdminLoginView,
    SwaggerDevTokenView,
    TenantDetailView,
    TenantListCreateView,
    TenantUserLoginView,
    TenantUserMeView,
    TenantUserRefreshView,
    TenantUserRegisterView,
    UserListView,
)

app_name = "tenants"

urlpatterns = [
    # Auth — tenant user
    path("auth/register/", TenantUserRegisterView.as_view(), name="register"),
    path("auth/login/", TenantUserLoginView.as_view(), name="login"),
    path("auth/refresh/", TenantUserRefreshView.as_view(), name="refresh"),
    path("auth/me/", TenantUserMeView.as_view(), name="me"),
    # Auth — platform super admin
    path("auth/admin/login/", AdminLoginView.as_view(), name="admin-login"),
    # Tenants
    path("tenants/", TenantListCreateView.as_view(), name="tenant-list-create"),
    path("tenants/users/", UserListView.as_view(), name="user-list"),
    path("tenants/<uuid:tenant_id>/", TenantDetailView.as_view(), name="tenant-detail"),
]

if settings.DEBUG:
    urlpatterns.append(
        path(
            "auth/admin/swagger-token/",
            SwaggerDevTokenView.as_view(),
            name="swagger-dev-token",
        )
    )
