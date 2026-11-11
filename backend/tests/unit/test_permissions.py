from types import SimpleNamespace

import pytest

from apps.core.permissions import IsAdmin, IsEngineerOrAdmin, ReadOnlyOrEngineer


def req(role, method="GET"):
    user = SimpleNamespace(is_authenticated=role is not None, role=role)
    return SimpleNamespace(user=user, method=method)


@pytest.mark.parametrize(
    "perm,role,method,allowed",
    [
        (IsAdmin, "admin", "GET", True),
        (IsAdmin, "engineer", "GET", False),
        (IsAdmin, "viewer", "GET", False),
        (IsAdmin, None, "GET", False),
        (IsEngineerOrAdmin, "admin", "POST", True),
        (IsEngineerOrAdmin, "engineer", "POST", True),
        (IsEngineerOrAdmin, "viewer", "GET", False),
        (ReadOnlyOrEngineer, "viewer", "GET", True),
        (ReadOnlyOrEngineer, "viewer", "HEAD", True),
        (ReadOnlyOrEngineer, "viewer", "POST", False),
        (ReadOnlyOrEngineer, "viewer", "PATCH", False),
        (ReadOnlyOrEngineer, "engineer", "PATCH", True),
        (ReadOnlyOrEngineer, "admin", "DELETE", True),
        (ReadOnlyOrEngineer, None, "GET", False),
    ],
)
def test_role_matrix(perm, role, method, allowed):
    assert perm().has_permission(req(role, method), view=None) is allowed
