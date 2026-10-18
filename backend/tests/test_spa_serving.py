import pytest
from django.core.handlers.wsgi import WSGIHandler
from django.test import RequestFactory, override_settings

SENTINEL = "SENTINEL-015"
SHELL = f'<!doctype html><div id="root">{SENTINEL}</div>'
MANIFEST = '{"name": "Sharelo"}'


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "index.html").write_text(SHELL)
    (tmp_path / "manifest.webmanifest").write_text(MANIFEST)
    return tmp_path


def fetch(directory, path):
    """Full stack incl. whitenoise. It indexes WHITENOISE_ROOT when the handler is built, so
    every call builds its own handler under the directory's settings."""
    with override_settings(FRONTEND_DIST=directory, WHITENOISE_ROOT=directory):
        handler = WSGIHandler()
        environ = RequestFactory().get(path, HTTP_HOST="localhost").environ
        seen = {}

        def start_response(status, headers, exc_info=None):
            seen["status"] = int(status.split()[0])
            seen["headers"] = {k.lower(): v for k, v in headers}

        body = b"".join(handler(environ, start_response)).decode()
    return seen["status"], seen["headers"], body


def test_unknown_api_path_is_not_the_spa_shell(dist):
    status, _, body = fetch(dist, "/api/does-not-exist/")
    assert status == 404
    assert SENTINEL not in body


@pytest.mark.parametrize("path", ["/api", "/admin", "/api/does-not-exist", "/admin/nope/"])
def test_bare_api_path_is_not_the_spa_shell(dist, path):
    _, _, body = fetch(dist, path)
    assert SENTINEL not in body


@pytest.mark.django_db
def test_known_api_route_still_answers_json(dist):
    status, headers, body = fetch(dist, "/api/me")
    assert headers["content-type"].startswith("application/json")
    assert SENTINEL not in body
    assert status in (200, 401, 403)


@pytest.mark.parametrize("path", ["/", "/g/1/expenses", "/join/abc", "/login"])
def test_deep_link_returns_index_html(dist, path):
    status, headers, body = fetch(dist, path)
    assert status == 200
    assert SENTINEL in body
    assert headers["cache-control"] == "no-cache"


def test_real_static_file_is_served_not_index(dist):
    status, _, body = fetch(dist, "/manifest.webmanifest")
    assert status == 200
    assert body == MANIFEST


def test_spa_view_404s_without_a_build(tmp_path):
    status, _, body = fetch(tmp_path, "/g/1/expenses")
    assert status == 404
    assert SENTINEL not in body


def test_each_request_reads_its_own_directory(dist, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    (other / "index.html").write_text("OTHER-SHELL")
    assert "OTHER-SHELL" in fetch(other, "/x")[2]
    assert SENTINEL in fetch(dist, "/x")[2]


def test_security_headers_on_spa_response(dist):
    _, headers, _ = fetch(dist, "/g/1/expenses")
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "same-origin"
