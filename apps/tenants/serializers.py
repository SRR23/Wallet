"""
Serializers for Tenant, tenant-user auth, and platform admin login.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.tenants.models import Tenant, User
from apps.tenants.services import create_user, update_user
from apps.tenants.tokens import issue_tenant_user_tokens, refresh_tenant_user_tokens


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "name", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class TenantCreateSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=255,
        help_text="Display name for the tenant (organization / merchant).",
    )

    def create(self, validated_data):
        from apps.tenants.services import create_tenant

        return create_tenant(name=validated_data["name"])


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "tenant", "email", "name", "created_at", "updated_at")
        read_only_fields = ("id", "tenant", "email", "created_at", "updated_at")


class TenantUserRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text="Unique within the tenant from X-Tenant-ID.",
    )
    name = serializers.CharField(
        max_length=255,
        help_text="Display name for the wallet owner.",
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text="Must pass Django password validators (min 8 chars).",
    )
    password_confirm = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text="Must match password.",
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        tenant = self.context["tenant"]
        email = validated_data["email"]
        if User.objects.filter(tenant=tenant, email=email).exists():
            raise serializers.ValidationError(
                {"email": "A user with this email already exists for this tenant."}
            )
        return create_user(
            tenant=tenant,
            email=email,
            name=validated_data["name"],
            password=validated_data["password"],
        )


class TenantUserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text="Email registered under the tenant in X-Tenant-ID.",
    )
    password = serializers.CharField(write_only=True, help_text="Account password.")

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate(self, attrs):
        tenant = self.context["tenant"]
        try:
            user = User.objects.get(tenant=tenant, email=attrs["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.check_password(attrs["password"]):
            raise serializers.ValidationError("Invalid email or password.")

        attrs["user"] = user
        return attrs

    def create_tokens(self) -> dict:
        user = self.validated_data["user"]
        payload = issue_tenant_user_tokens(user)
        payload["user"] = UserSerializer(user).data
        return payload


class TenantUserRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        help_text="Tenant-user refresh token from register or login (not admin refresh).",
    )

    def create_tokens(self) -> dict:
        return refresh_tenant_user_tokens(self.validated_data["refresh"])


class TenantUserProfileUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=255,
        required=False,
        help_text="New display name. Email and tenant are not editable here.",
    )

    def update(self, instance, validated_data):
        return update_user(user=instance, name=validated_data.get("name"))


class AdminProfileSerializer(serializers.ModelSerializer):
    """Django AUTH_USER_MODEL profile returned from admin login."""

    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "is_superuser", "date_joined")
        read_only_fields = fields


class AdminLoginSerializer(TokenObtainPairSerializer):
    """Platform super-admin login. Only is_superuser may proceed."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["is_superuser"] = user.is_superuser
        token["principal"] = "platform_admin"
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_superuser:
            from rest_framework.exceptions import AuthenticationFailed

            raise AuthenticationFailed("Only a super admin can use this login.")
        data["user"] = AdminProfileSerializer(self.user).data
        return data
