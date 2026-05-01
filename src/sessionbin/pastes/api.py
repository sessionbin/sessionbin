from typing import cast

from django.conf import settings
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.crypto import constant_time_compare
from ninja import File, Header, Router, Status
from ninja.files import UploadedFile

from sessionbin.pastes.models import Paste, hash_token
from sessionbin.pastes.services import create_paste_from_upload, delete_paste

router = Router()


@router.post("/upload")
def upload(request: HttpRequest, file: UploadedFile = File(...)):
    max_bytes = cast(int, settings.SESSIONBIN["MAX_UPLOAD_BYTES"])
    if file.size and file.size > max_bytes:
        return JsonResponse({"error": "file too large", "max_bytes": max_bytes}, status=413)
    raw = file.read()
    paste, delete_token = create_paste_from_upload(
        raw=raw,
        uploader_ip=request.META.get("REMOTE_ADDR"),
    )
    return {
        "slug": paste.slug,
        "url": request.build_absolute_uri(paste.url),
        "delete_token": delete_token,
    }


@router.delete("/p/{slug}", response={204: None, 404: dict})
def api_delete(request: HttpRequest, slug: str, x_delete_token: str = Header(...)):
    paste = get_object_or_404(Paste, slug=slug)
    if not constant_time_compare(paste.delete_token_hash, hash_token(x_delete_token)):
        raise Http404
    delete_paste(paste)
    return Status(204, None)
