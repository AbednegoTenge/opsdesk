"""Response headers for a JSON API. Django's SecurityMiddleware covers HSTS, nosniff,
referrer policy and COOP; this adds what it doesn't."""

from django.conf import settings

# Nothing an API response contains should ever run, load, or be framed.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # The Swagger UI page loads its scripts from a CDN, so it keeps a looser policy.
        self.docs_path = "/api/v1/docs/"

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        if not path.startswith(self.docs_path):
            response.setdefault("Content-Security-Policy", API_CSP)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        if path.startswith("/api/") or path.startswith("/health/"):
            # Incident data and tokens must not be kept by browsers or shared proxies.
            if "Cache-Control" not in response:
                response["Cache-Control"] = "no-store"
        if getattr(settings, "APP_VERSION", ""):
            response.setdefault("X-OpsDesk-Version", settings.APP_VERSION)
        return response
