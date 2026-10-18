from django.conf import settings
from django.http import Http404, HttpResponse
from django.views import View


class SpaIndexView(View):
    """The app shell for client-side routes. Read per request: the file is small and a cache
    would leak one directory's answer into another's (tests, or a rebuild while running)."""

    def get(self, request, *args, **kwargs):
        try:
            html = (settings.FRONTEND_DIST / "index.html").read_bytes()
        except FileNotFoundError:
            raise Http404("frontend not built") from None
        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["Cache-Control"] = "no-cache"
        return response
