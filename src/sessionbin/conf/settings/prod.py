import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable is required")

DEBUG = False

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

# Derived so one env var drives both and the two cannot drift apart.
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h != "*"]

# Proxy headers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Both are production-only: WhiteNoise because DEBUG serves static itself, ClientIPMiddleware
# because the header is only trustworthy with a proxy in front. Positions are load-bearing:
# WhiteNoise directly after SecurityMiddleware, ClientIP ahead of anything reading the address.
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
MIDDLEWARE.insert(0, "sessionbin.conf.middleware.ClientIPMiddleware")

# Security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 15768000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_SECURE = True

SESSIONBIN["CSP_ENABLED"] = True  # noqa: F405

# Shared by both gunicorn workers; per-process LocMemCache would double every limit.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.getenv("SESSIONBIN_CACHE_DIR", str(BASE_DIR / "cache")),  # noqa: F405
    }
}
