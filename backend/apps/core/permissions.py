"""Role-based permission classes. Roles live on the User model (apps.users.models.Role)."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import Role


def _role(request) -> str | None:
    user = request.user
    if not user or not user.is_authenticated:
        return None
    return user.role


class IsAdmin(BasePermission):
    message = "Only Admins can perform this action."

    def has_permission(self, request, view) -> bool:
        return _role(request) == Role.ADMIN


class IsEngineerOrAdmin(BasePermission):
    message = "Only Engineers and Admins can perform this action."

    def has_permission(self, request, view) -> bool:
        return _role(request) in (Role.ENGINEER, Role.ADMIN)


class ReadOnlyOrEngineer(BasePermission):
    """Any authenticated role may read; only Engineers and Admins may write."""

    message = "Viewers have read-only access."

    def has_permission(self, request, view) -> bool:
        role = _role(request)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        return role in (Role.ENGINEER, Role.ADMIN)
