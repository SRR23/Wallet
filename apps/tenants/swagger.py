"""
Swagger UI view that auto-authorizes a local superuser when DEBUG=True.
"""
from django.conf import settings
from django.urls import reverse
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularSwaggerView


@extend_schema(exclude=True)
class WalletSwaggerView(SpectacularSwaggerView):
    """
    SpectacularSwaggerView builds template context in get(), not get_context_data.
    Inject DEBUG auto-auth fields into that response data.
    """

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if settings.DEBUG:
            response.data["debug_swagger_auto_auth"] = True
            response.data["swagger_dev_token_url"] = reverse("tenants:swagger-dev-token")
        else:
            response.data["debug_swagger_auto_auth"] = False
            response.data["swagger_dev_token_url"] = ""
        return response
