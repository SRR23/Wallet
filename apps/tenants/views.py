"""
Tenant, auth, and super-admin API views.

All login/register/refresh/me and admin login live here.
"""
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.authentication import (
    TENANT_HEADER,
    RequiredTenantHeaderAuthentication,
    TenantHeaderAuthentication,
    TenantUserJWTAuthentication,
)
from apps.tenants.models import Tenant, User
from apps.tenants.serializers import (
    AdminLoginSerializer,
    TenantCreateSerializer,
    TenantSerializer,
    TenantUserLoginSerializer,
    TenantUserProfileUpdateSerializer,
    TenantUserRefreshSerializer,
    TenantUserRegisterSerializer,
    UserSerializer,
)
from apps.tenants.tokens import (
    PRINCIPAL_TENANT_USER,
    TenantUserRefreshToken,
    issue_tenant_user_tokens,
    refresh_tenant_user_tokens,
)
from apps.wallets.serializers import WalletSerializer
from utils.permissions import IsSuperUser

AuthUser = get_user_model()

TENANT_HEADER_PARAMETER = OpenApiParameter(
    name=TENANT_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "Optional tenant UUID. When present, the user list is filtered to that "
        "tenant only. Omit to list users across all tenants."
    ),
)

TENANT_HEADER_REQUIRED = OpenApiParameter(
    name=TENANT_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "Required tenant UUID. Must match the tenant that owns the user / wallet. "
        "For JWT calls, must also match the tenant_id claim inside the access token."
    ),
)


# ---------------------------------------------------------------------------
# Tenant CRUD / admin lists
# ---------------------------------------------------------------------------


class TenantListCreateView(APIView):
    """GET: list tenants (super admin). POST: create tenant (open)."""

    def get_authenticators(self):
        request = getattr(self, "request", None)
        if request is None or getattr(self, "swagger_fake_view", False):
            return [JWTAuthentication()]
        if request.method == "POST":
            return []
        return [JWTAuthentication()]

    def get_permissions(self):
        request = getattr(self, "request", None)
        if request is None or getattr(self, "swagger_fake_view", False):
            return [AllowAny()]
        if request.method == "POST":
            return [AllowAny()]
        return [IsSuperUser()]

    @extend_schema(
        tags=["tenants"],
        summary="List all tenants",
        description=(
            "Returns every tenant on the platform.\n\n"
            "**Who:** platform super admin only "
            "(login via `POST /api/auth/admin/login/`, then Authorize with the access token).\n\n"
            "Normal tenant users cannot call this."
        ),
        responses={200: TenantSerializer(many=True)},
    )
    def get(self, request):
        tenants = Tenant.objects.all()
        return Response(TenantSerializer(tenants, many=True).data)

    @extend_schema(
        tags=["tenants"],
        summary="Create a tenant",
        description=(
            "Creates a new tenant (organization / merchant).\n\n"
            "**Who:** public — no auth required.\n\n"
            "Save the returned `id` and send it as the `X-Tenant-ID` header on "
            "register, login, and all wallet/ledger calls for that tenant."
        ),
        request=TenantCreateSerializer,
        responses={201: TenantSerializer},
    )
    def post(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        return Response(
            TenantSerializer(tenant).data,
            status=status.HTTP_201_CREATED,
        )


class TenantDetailView(APIView):
    """Fetch one tenant by id. Super admin only."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperUser]

    @extend_schema(
        tags=["tenants"],
        summary="Get tenant details",
        description=(
            "Returns a single tenant by UUID.\n\n"
            "**Who:** platform super admin only."
        ),
        responses={200: TenantSerializer},
    )
    def get(self, request, tenant_id):
        tenant = get_object_or_404(Tenant, pk=tenant_id)
        return Response(TenantSerializer(tenant).data)


class UserListView(APIView):
    """List domain users. Super admin only. Optional X-Tenant-ID filter."""

    authentication_classes = [JWTAuthentication, TenantHeaderAuthentication]
    permission_classes = [IsSuperUser]

    @extend_schema(
        tags=["users"],
        summary="List tenant users (wallet owners)",
        description=(
            "Lists domain users (`tenants.User`), not Django admin accounts.\n\n"
            "**Who:** platform super admin only.\n\n"
            "Optional `X-Tenant-ID` header filters to one tenant. "
            "Without it, users from all tenants are returned."
        ),
        parameters=[TENANT_HEADER_PARAMETER],
        responses={200: UserSerializer(many=True)},
    )
    def get(self, request):
        users = User.objects.select_related("tenant").all()
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            users = users.filter(tenant=tenant)
        return Response(UserSerializer(users, many=True).data)


# ---------------------------------------------------------------------------
# Tenant-user auth (X-Tenant-ID required)
# ---------------------------------------------------------------------------


class TenantUserRegisterView(APIView):
    """Register a tenants.User under X-Tenant-ID and return tokens."""

    authentication_classes = [RequiredTenantHeaderAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Register a tenant user (opens wallet)",
        description=(
            "Creates a user **under the tenant in `X-Tenant-ID`**, hashes the password, "
            "and auto-creates a zero-balance wallet (`currency=BDT`).\n\n"
            "**Headers:** `X-Tenant-ID` required.\n\n"
            "**Response includes:** `user`, `wallet`, `access`, and `refresh` tokens "
            "so the client is logged in immediately.\n\n"
            "Email must be unique within that tenant."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=TenantUserRegisterSerializer,
        responses={201: UserSerializer},
    )
    def post(self, request):
        serializer = TenantUserRegisterSerializer(
            data=request.data,
            context={"tenant": request.tenant},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = issue_tenant_user_tokens(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "wallet": WalletSerializer(user.wallet).data,
                **tokens,
            },
            status=status.HTTP_201_CREATED,
        )


class TenantUserLoginView(APIView):
    """Login a tenants.User under X-Tenant-ID."""

    authentication_classes = [RequiredTenantHeaderAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Login as a tenant user",
        description=(
            "Authenticates a domain user with email + password **inside one tenant**.\n\n"
            "**Headers:** `X-Tenant-ID` required (the tenant where the user registered).\n\n"
            "Returns `access`, `refresh`, and `user`. Use the access token as "
            "`Authorization: Bearer <access>` together with the same `X-Tenant-ID` "
            "on wallet and ledger endpoints."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=TenantUserLoginSerializer,
        responses={200: TenantUserLoginSerializer},
    )
    def post(self, request):
        serializer = TenantUserLoginSerializer(
            data=request.data,
            context={"tenant": request.tenant},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.create_tokens(), status=status.HTTP_200_OK)


class TenantUserRefreshView(APIView):
    """Refresh a tenant-user JWT. X-Tenant-ID must match the token tenant."""

    authentication_classes = [RequiredTenantHeaderAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Refresh tenant-user access token",
        description=(
            "Exchanges a tenant-user refresh token for a new access (and refresh) pair.\n\n"
            "**Headers:** `X-Tenant-ID` required and must match the `tenant_id` "
            "stored inside the refresh token.\n\n"
            "Do not use a platform super-admin refresh token here."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=TenantUserRefreshSerializer,
        responses={200: TenantUserRefreshSerializer},
    )
    def post(self, request):
        serializer = TenantUserRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_refresh = serializer.validated_data["refresh"]
        try:
            refresh = TenantUserRefreshToken(raw_refresh)
            if refresh.get("principal") != PRINCIPAL_TENANT_USER:
                raise InvalidToken("Not a tenant-user refresh token.")
            if str(refresh["tenant_id"]) != str(request.tenant.id):
                raise InvalidToken(
                    f"{TENANT_HEADER} does not match the refresh token tenant."
                )
            tokens = refresh_tenant_user_tokens(raw_refresh)
        except (InvalidToken, TokenError) as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            return Response(
                {"error": "authentication_failed", "detail": detail},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(tokens, status=status.HTTP_200_OK)


class TenantUserMeView(APIView):
    """GET/PATCH the authenticated tenant user. Requires JWT + matching X-Tenant-ID."""

    authentication_classes = [TenantUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Get my tenant-user profile",
        description=(
            "Returns the currently authenticated tenant user.\n\n"
            "**Headers:** `Authorization: Bearer <tenant access>` and matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        responses={200: UserSerializer},
    )
    def get(self, request):
        return Response(UserSerializer(request.tenant_user).data)

    @extend_schema(
        tags=["auth"],
        summary="Update my tenant-user profile",
        description=(
            "Partially updates the authenticated tenant user (currently `name` only).\n\n"
            "Email and tenant cannot be changed here.\n\n"
            "**Headers:** Bearer tenant JWT + matching `X-Tenant-ID`."
        ),
        parameters=[TENANT_HEADER_REQUIRED],
        request=TenantUserProfileUpdateSerializer,
        responses={200: UserSerializer},
    )
    def patch(self, request):
        serializer = TenantUserProfileUpdateSerializer(
            instance=request.tenant_user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data)


# ---------------------------------------------------------------------------
# Platform super-admin login
# ---------------------------------------------------------------------------


class AdminLoginView(APIView):
    """Django superuser login → platform JWT for tenant list/detail APIs."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Login as platform super admin",
        description=(
            "Logs in a Django **superuser** (created with `createsuperuser`).\n\n"
            "Returns a platform JWT used only for admin APIs such as listing tenants "
            "and listing all users.\n\n"
            "This is **not** tenant-user login. Non-superuser accounts are rejected.\n\n"
            "In DEBUG, Swagger may auto-authorize a local swagger superuser; "
            "you can still call this endpoint manually."
        ),
        request=AdminLoginSerializer,
        responses={200: AdminLoginSerializer},
    )
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class SwaggerDevTokenView(APIView):
    """
    DEBUG only: return a superuser access token for Swagger auto-authorize.

    Uses SWAGGER_SUPERUSER_USERNAME / SWAGGER_SUPERUSER_PASSWORD from .env.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request):
        if not settings.DEBUG:
            return Response(
                {"error": "not_found", "detail": "Not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        username = os.environ.get("SWAGGER_SUPERUSER_USERNAME", "swagger").strip()
        password = os.environ.get("SWAGGER_SUPERUSER_PASSWORD", "swagger-admin-pass")

        user, created = AuthUser.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@localhost",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()

        refresh = RefreshToken.for_user(user)
        refresh["principal"] = "platform_admin"
        refresh["username"] = user.username
        refresh["is_superuser"] = True
        access = refresh.access_token
        access["principal"] = "platform_admin"
        access["username"] = user.username
        access["is_superuser"] = True

        return Response(
            {
                "access": str(access),
                "username": user.username,
                "created": created,
            }
        )
