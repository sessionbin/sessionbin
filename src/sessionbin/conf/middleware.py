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
    """Rewrite REMOTE_ADDR from the last X-Forwarded-For entry.

    Behind a proxy REMOTE_ADDR is the proxy itself, so uploader_ip records nothing usable
    for abuse triage. A proxy appends the peer it actually saw, so the last entry is the
    only one a client cannot forge by sending its own header.

    Enabled in prod settings alone, because that trust is only earned when a proxy is in
    front. It also assumes exactly one: put a CDN ahead of Caddy and the last entry becomes
    the CDN's edge, not the client.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            request.META["REMOTE_ADDR"] = forwarded.rpartition(",")[2].strip()
        return self.get_response(request)
