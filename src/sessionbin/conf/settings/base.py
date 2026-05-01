import os
import shutil
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "sessionbin.pastes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "sessionbin.conf.middleware.CSPMiddleware",
]

ROOT_URLCONF = "sessionbin.conf.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "sessionbin.pastes.context_processors.sessionbin",
            ],
        },
    },
]

WSGI_APPLICATION = "sessionbin.conf.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("SESSIONBIN_DB_PATH", BASE_DIR / "sessionbin.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

DATA_UPLOAD_MAX_MEMORY_SIZE = _MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = _MAX_UPLOAD_BYTES

SESSIONBIN = {
    "STORAGE_BACKEND": "filesystem",
    "DATA_DIR": Path(os.getenv("SESSIONBIN_DATA_DIR", BASE_DIR.parent.parent / "data")),
    "MAX_UPLOAD_BYTES": _MAX_UPLOAD_BYTES,
    "MAX_UPLOAD_MB": _MAX_UPLOAD_BYTES // (1024 * 1024),
    "GITHUB_URL": os.environ.get(
        "SESSIONBIN_GITHUB_URL", "https://github.com/sessionbin/sessionbin"
    ),
    "CSP_ENABLED": False,
    "FOOTER_POSTAMBLE": os.getenv("SESSIONBIN_FOOTER_POSTAMBLE"),
    "FOOTER_FEEDBACK_URL": os.getenv("SESSIONBIN_FOOTER_FEEDBACK_URL"),
    "FOOTER_FEEDBACK_LABEL": os.getenv("SESSIONBIN_FOOTER_FEEDBACK_LABEL", "Feedback"),
}

# Logging

_log_file = os.getenv("SESSIONBIN_LOG_FILE")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        **(
            {
                "file": {
                    "class": "logging.FileHandler",
                    "filename": _log_file,
                    "formatter": "standard",
                }
            }
            if _log_file
            else {}
        ),
    },
    "root": {
        "handlers": ["console"] + (["file"] if _log_file else []),
        "level": "INFO",
    },
    "loggers": {
        "sessionbin": {
            "level": "DEBUG",
            "propagate": True,
        },
    },
}

# Require gitleaks to be installed

if not shutil.which("gitleaks"):
    raise ImproperlyConfigured(
        "gitleaks is not installed or not on PATH. "
        "Install it from https://github.com/gitleaks/gitleaks"
    )
