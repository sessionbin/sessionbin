from django.contrib import admin
from django.utils import timezone

from .models import Paste


@admin.register(Paste)
class PasteAdmin(admin.ModelAdmin):
    list_display = ["slug", "sha256_short", "size_bytes", "created_at", "is_deleted"]
    list_filter = ["created_at"]
    search_fields = ["slug", "sha256"]
    readonly_fields = ["slug", "delete_token_hash", "sha256", "created_at"]
    actions = ["soft_delete"]

    @admin.display(description="sha256")
    def sha256_short(self, obj: Paste) -> str:
        return obj.sha256[:12] + "..."

    @admin.display(boolean=True, description="deleted")
    def is_deleted(self, obj: Paste) -> bool:
        return obj.is_deleted

    @admin.action(description="Soft-delete selected pastes")
    def soft_delete(self, request, queryset):
        queryset.filter(deleted_at__isnull=True).update(deleted_at=timezone.now())
