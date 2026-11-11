import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import ServiceUnavailable
from apps.users import token_store

from ..factories import UserFactory

pytestmark = pytest.mark.django_db


def test_token_can_be_consumed_exactly_once():
    token = token_store.issue_for(UserFactory())
    assert token_store.consume(token) is True
    assert token_store.consume(token) is False


def test_unrecorded_token_is_rejected():
    assert token_store.consume(RefreshToken.for_user(UserFactory())) is False


def test_key_expires_with_the_token(fake_redis):
    token = token_store.issue_for(UserFactory())
    ttl = fake_redis.ttl(token_store._token_key(token["jti"]))
    assert 0 < ttl <= 7 * 24 * 3600


def test_revoke_all_only_touches_that_user():
    alice, bob = UserFactory(), UserFactory()
    a1, a2, b1 = (
        token_store.issue_for(alice),
        token_store.issue_for(alice),
        token_store.issue_for(bob),
    )
    assert token_store.revoke_all(alice.pk) == 2
    assert not token_store.consume(a1)
    assert not token_store.consume(a2)
    assert token_store.consume(b1)


def test_access_token_carries_role():
    user = UserFactory(role="engineer")
    assert token_store.issue_for(user).access_token["role"] == "engineer"


def test_redis_errors_become_service_unavailable(redis_down):
    with pytest.raises(ServiceUnavailable):
        token_store.issue_for(UserFactory())
