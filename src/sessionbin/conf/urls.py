from django.http import JsonResponse
from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import path, re_path
from ninja import NinjaAPI

from sessionbin.pastes.api import router as pastes_router
from sessionbin.pastes.models import Paste
from sessionbin.pastes.views import manage_paste, raw_paste, upload_view, view_paste

api = NinjaAPI()


@api.get("/health")
def health(request):
    return {"status": "ok", "pastes": Paste.objects.filter(deleted_at__isnull=True).count()}


api.add_router("/", pastes_router)


def api_not_found(request):
    """Keep an unrouted /api/ path in JSON; only Ninja's own 404s go through Ninja."""
    return JsonResponse({"detail": "Not Found"}, status=404)


def favicon(request):
    """Route the path crawlers probe by convention; templates link the static one.

    Not permanent, because a cached 301 would outlive a deployment changing STATIC_URL.
    """
    return redirect(static("favicon.ico"))


urlpatterns = [
    path("favicon.ico", favicon),
    # Ninja routes /api/ itself, to a view that raises Http404; claim it first.
    path("api/", api_not_found),
    path("api/", api.urls),
    re_path(r"^api/", api_not_found),
    path("raw/<slug:slug>.jsonl", raw_paste, name="raw-paste"),
    path("p/<slug:slug>/", view_paste, name="view-paste"),
    path("p/<slug:slug>/manage/", manage_paste, name="manage-paste"),
    path("", upload_view, name="upload"),
]
