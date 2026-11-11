"""Rate limits for the sign-in endpoints.

Counters live in the shared cache (Redis in every deployed environment), so a limit holds
across all API replicas. If the cache is unreachable the throttles fail open and log: being
briefly unthrottled is better than refusing every sign-in.

Client IPs come from REMOTE_ADDR, or from X-Forwarded-For when NUM_PROXIES says how many
trusted proxies (load balancer, ingress) sit in front of the API.
"""

import hashlib
import logging

from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


class FailOpenThrottle(SimpleRateThrottle):
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:  # cache backend down or misconfigured
            logger.warning(
                "rate-limit cache unavailable; allowing request", extra={"scope": self.scope}
            )
            return True


class _PerIP(FailOpenThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginIPThrottle(_PerIP):
    """Caps sign-in attempts from one address (password spraying, scripted guessing)."""

    scope = "auth_login"


class LoginAccountThrottle(FailOpenThrottle):
    """Caps sign-in attempts against one account from anywhere (credential stuffing)."""

    scope = "auth_login_account"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if hasattr(request.data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return None  # nothing to key on; the per-IP limit still applies
        digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class RegisterThrottle(_PerIP):
    scope = "auth_register"


class RefreshThrottle(_PerIP):
    """Generous: every open tab refreshes, and offices share one address."""

    scope = "auth_refresh"


class PasswordChangeThrottle(FailOpenThrottle):
    scope = "auth_password"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
