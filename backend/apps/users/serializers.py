from django.contrib.auth import authenticate, password_validation
from rest_framework import serializers

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_active", "date_joined"]
        read_only_fields = fields


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name"]


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name", "role", "is_active"]

    def validate(self, attrs):
        request = self.context["request"]
        if self.instance and self.instance.pk == request.user.pk:
            if "role" in attrs and attrs["role"] != Role.ADMIN:
                raise serializers.ValidationError(
                    {"role": "You cannot remove your own Admin role."}
                )
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "You cannot deactivate yourself."})
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["email", "full_name", "password"]

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], full_name=attrs.get("full_name", ""))
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(role=Role.VIEWER, **validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None or not user.is_active:
            # Same message for unknown email, wrong password and inactive user.
            raise serializers.ValidationError("Invalid email or password.", code="invalid_login")
        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(
            attrs["new_password"], user=self.context["request"].user
        )
        return attrs


class AuthResponseSerializer(serializers.Serializer):
    """Shape of login/refresh responses (for the OpenAPI schema)."""

    access = serializers.CharField()
    user = UserSerializer()
