"""
Root URL configuration.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView
from rest_framework.permissions import AllowAny

from apps.tenants.swagger import WalletSwaggerView


def health_check(_request):
    """Liveness check for local runs and Docker. Not part of the wallet API."""
    return JsonResponse({"status": "ok"})


class PublicSchemaView(SpectacularAPIView):
    """
    OpenAPI schema must stay reachable even when Swagger Authorize holds a
    tenant-user JWT. Default JWTAuthentication would reject that token (it is
    not a Django AUTH_USER_MODEL user) and return 401, breaking /api/docs/.
    """

    authentication_classes = []
    permission_classes = [AllowAny]


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health-check"),
    path("api/schema/", PublicSchemaView.as_view(), name="schema"),
    path("api/docs/", WalletSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Auth + tenants routes (all login/register live in apps.tenants.views).
    path("api/", include("apps.tenants.urls")),
    path("api/wallets/", include("apps.wallets.urls")),
    path("api/ledger/", include("apps.ledger.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
