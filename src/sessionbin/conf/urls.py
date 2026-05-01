from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from sessionbin.pastes.api import router as pastes_router
from sessionbin.pastes.models import Paste
from sessionbin.pastes.views import manage_paste, raw_paste, upload_view, view_paste

api = NinjaAPI()


@api.get("/health")
def health(request):
    return {"status": "ok", "pastes": Paste.objects.filter(deleted_at__isnull=True).count()}


api.add_router("/", pastes_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("raw/<slug:slug>.jsonl", raw_paste, name="raw-paste"),
    path("p/<slug:slug>/", view_paste, name="view-paste"),
    path("p/<slug:slug>/manage/", manage_paste, name="manage-paste"),
    path("", upload_view, name="upload"),
]
