import logging

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.permissions import IsAdmin, IsEngineerOrAdmin

from . import token_store
from .models import User
from .serializers import (
    AdminUserUpdateSerializer,
    AuthResponseSerializer,
    LoginSerializer,
    MeUpdateSerializer,
    PasswordChangeSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


# --- cookie helpers ---------------------------------------------------------
def _set_refresh_cookie(response: Response, refresh: RefreshToken) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        path=settings.REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        path=settings.REFRESH_COOKIE_PATH,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _raw_refresh(request) -> str | None:
    # Browsers send the httpOnly cookie; non-browser clients may send it in the body.
    return request.COOKIES.get(settings.REFRESH_COOKIE_NAME) or request.data.get("refresh")


def _auth_response(user: User, refresh: RefreshToken, status_code=status.HTTP_200_OK) -> Response:
    response = Response(
        {"access": str(refresh.access_token), "user": UserSerializer(user).data},
        status=status_code,
    )
    _set_refresh_cookie(response, refresh)
    return response


class PublicAuthView(APIView):
    """Endpoints that must work without (or with a stale) access token.

    They skip bearer authentication but still answer 401, not 403, on bad credentials.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'


# --- auth endpoints ---------------------------------------------------------
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def create(self, request, *args, **kwargs):
        if not settings.ALLOW_REGISTRATION:
            raise PermissionDenied("Self-registration is disabled. Ask an Admin for an account.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info("user registered", extra={"user_id": user.pk})
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(PublicAuthView):
    @extend_schema(request=LoginSerializer, responses=AuthResponseSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            raise AuthenticationFailed("Invalid email or password.", code="invalid_login")
        user = serializer.validated_data["user"]
        refresh = token_store.issue_for(user)
        User.objects.filter(pk=user.pk).update(last_login=refresh.current_time)
        logger.info("user logged in", extra={"user_id": user.pk})
        return _auth_response(user, refresh)


class RefreshView(PublicAuthView):
    """Rotate the refresh token: the old one is consumed, a new pair is issued."""

    @extend_schema(request=None, responses=AuthResponseSerializer)
    def post(self, request):
        raw = _raw_refresh(request)
        if not raw:
            raise AuthenticationFailed("No refresh token provided.", code="no_refresh_token")
        try:
            old = RefreshToken(raw)
        except TokenError as exc:
            raise AuthenticationFailed(
                "Refresh token is invalid or expired.", code="token_not_valid"
            ) from exc

        if not token_store.consume(old):
            logger.warning(
                "refresh token reuse or revoked token", extra={"user_id": old["user_id"]}
            )
            raise AuthenticationFailed("Refresh token has been revoked.", code="token_revoked")

        user = User.objects.filter(pk=old["user_id"], is_active=True).first()
        if user is None:
            raise AuthenticationFailed(
                "User is inactive or no longer exists.", code="user_inactive"
            )
        return _auth_response(user, token_store.issue_for(user))


class LogoutView(PublicAuthView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        raw = _raw_refresh(request)
        if raw:
            try:
                token_store.revoke(RefreshToken(raw))
            except TokenError:
                pass  # already invalid or expired: nothing to revoke
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "options"]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        return MeUpdateSerializer if self.request.method == "PATCH" else UserSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(UserSerializer(self.get_object()).data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        # Every existing session must log in again with the new password.
        token_store.revoke_all(user.pk)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


# --- user management --------------------------------------------------------
class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all()
    http_method_names = ["get", "patch", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update"):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated(), IsEngineerOrAdmin()]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return AdminUserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if role := params.get("role"):
            qs = qs.filter(role=role)
        if (active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        if search := params.get("search"):
            qs = qs.filter(email__icontains=search) | qs.filter(full_name__icontains=search)
        return qs.order_by("email")

    def perform_update(self, serializer):
        before = serializer.instance
        old_role, old_active = before.role, before.is_active
        with transaction.atomic():
            user = serializer.save()
        if user.role != old_role or user.is_active != old_active:
            # Role or status changed: force a fresh login so new tokens carry the new role.
            token_store.revoke_all(user.pk)
            logger.info(
                "user access changed",
                extra={"user_id": user.pk, "role": user.role, "is_active": user.is_active},
            )

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(UserSerializer(self.get_object()).data)
