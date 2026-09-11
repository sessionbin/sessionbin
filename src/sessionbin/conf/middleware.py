from django.conf import settings
from django.http import HttpRequest, HttpResponse

CSP_POLICY = "; ".join(
    [
        "default-src 'none'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)


class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if settings.SESSIONBIN.get("CSP_ENABLED"):
            response["Content-Security-Policy"] = CSP_POLICY
        return response


class ClientIPMiddleware:
    """REMOTE_ADDR from the last X-Forwarded-For entry, the one the proxy appended and a
    client cannot forge. Assumes exactly one proxy, and prod settings alone enable it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            request.META["REMOTE_ADDR"] = forwarded.rpartition(",")[2].strip()
        return self.get_response(request)
