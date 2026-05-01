from typing import Any

from django.conf import settings
from django.http import HttpRequest


def sessionbin(request: HttpRequest) -> dict[str, Any]:
    return {
        "github_url": settings.SESSIONBIN.get("GITHUB_URL"),
        "max_upload_mb": settings.SESSIONBIN.get("MAX_UPLOAD_MB"),
        "max_upload_bytes": settings.SESSIONBIN.get("MAX_UPLOAD_BYTES"),
        "footer_postamble": settings.SESSIONBIN.get("FOOTER_POSTAMBLE"),
        "footer_feedback_url": settings.SESSIONBIN.get("FOOTER_FEEDBACK_URL"),
        "footer_feedback_label": settings.SESSIONBIN.get("FOOTER_FEEDBACK_LABEL", "Feedback"),
    }
