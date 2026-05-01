import hashlib

from django.db import models
from django.utils.crypto import get_random_string

SLUG_ALPHABET = "abcdefghijkmnopqrstuvwxyz23456789"
SLUG_LENGTH = 10
DELETE_TOKEN_LENGTH = 32


def _make_slug() -> str:
    return get_random_string(SLUG_LENGTH, SLUG_ALPHABET)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Paste(models.Model):
    slug = models.CharField(max_length=SLUG_LENGTH, primary_key=True, default=_make_slug)
    delete_token_hash = models.CharField(max_length=64)
    sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.PositiveIntegerField()
    renderer_version = models.PositiveSmallIntegerField()
    adapter_version = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    uploader_ip = models.GenericIPAddressField(null=True, blank=True)
    harness = models.CharField(max_length=64, null=True, blank=True)
    session_model = models.CharField(max_length=128, null=True, blank=True)
    turn_count = models.PositiveIntegerField(null=True, blank=True)
    tool_call_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return self.slug

    @property
    def url(self) -> str:
        return f"/p/{self.slug}/"

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
