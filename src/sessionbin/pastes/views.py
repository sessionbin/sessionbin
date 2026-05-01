from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET, require_http_methods

from sessionbin.pastes.forms import UploadForm
from sessionbin.pastes.models import Paste, hash_token
from sessionbin.pastes.services import create_paste_from_upload, delete_paste
from sessionbin.storage.exceptions import NotFoundError
from sessionbin.storage.factory import get_storage


def _build_og_description(paste: Paste) -> str:
    if not paste.harness:
        return "Agentic coding session transcript on sessionbin."
    parts = [f"{paste.harness} session"]
    if paste.session_model:
        parts[0] += f" ({paste.session_model})"
    stats = []
    if paste.turn_count is not None:
        stats.append(f"{paste.turn_count} turns")
    if paste.tool_call_count is not None:
        stats.append(f"{paste.tool_call_count} tool calls")
    if stats:
        parts.append(", ".join(stats))
    desc = " — ".join(parts)
    if len(desc) > 250:
        return desc[:247] + "..."
    return desc


@require_GET
@cache_control(public=True, max_age=86400)
def view_paste(request, slug: str):
    paste = get_object_or_404(Paste, slug=slug)
    if paste.is_deleted:
        raise Http404
    storage = get_storage()
    try:
        fragment = storage.read_fragment(slug)
    except NotFoundError:
        raise Http404
    og_description = _build_og_description(paste)
    return render(
        request,
        "pastes/paste.html",
        {
            "paste": paste,
            "fragment": fragment,
            "og_description": og_description,
        },
    )


@require_GET
@cache_control(public=True, max_age=86400)
def raw_paste(request, slug: str):
    paste = get_object_or_404(Paste, slug=slug)
    if paste.is_deleted:
        raise Http404
    storage = get_storage()
    try:
        data = storage.read_raw(slug)
    except NotFoundError:
        raise Http404
    response = HttpResponse(data, content_type="application/jsonl")
    response["Content-Encoding"] = "gzip"
    response["Content-Disposition"] = f'attachment; filename="{slug}.jsonl"'
    return response


@require_http_methods(["GET", "POST"])
def upload_view(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["file"].read()
        paste, delete_token = create_paste_from_upload(
            raw=raw,
            uploader_ip=request.META.get("REMOTE_ADDR"),
        )
        return redirect(f"{paste.url}manage/?token={delete_token}")
    return render(request, "pastes/landing.html", {"form": form})


@require_http_methods(["GET", "POST"])
def manage_paste(request, slug: str):
    paste = get_object_or_404(Paste, slug=slug)
    token = request.GET.get("token", "")
    if not constant_time_compare(paste.delete_token_hash, hash_token(token)):
        raise Http404

    if request.method == "POST" and paste.deleted_at is None:
        delete_paste(paste)
        return redirect(f"{request.path}?token={token}")

    manage_url = f"{paste.url}manage/?token={token}"
    return render(request, "pastes/manage.html", {"paste": paste, "manage_url": manage_url})
