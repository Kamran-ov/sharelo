from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .spa import SpaIndexView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/", include("accounts.api.urls")),
    path("api/", include("ledger.api.urls")),
    # Last, so every real route wins. The exclusion keeps unknown /api/ and /admin/ paths from
    # answering with the shell; the regex sees paths without the leading slash.
    re_path(r"^(?!api(/|$)|admin(/|$)|static/).*$", SpaIndexView.as_view()),
]
