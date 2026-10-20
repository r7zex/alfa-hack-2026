"""Regression tests for serving the client through the normal FastAPI entrypoint."""

import os
import mimetypes

import pytest

os.environ.setdefault("DB_PASSWORD", "unit-test-only")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_root_serves_frontend() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Делора" in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/app.js", "javascript"),
        ("/styles.css", "text/css"),
        ("/js/domain.mjs", "javascript"),
        ("/js/store.mjs", "javascript"),
        ("/favicon.svg", "image/svg+xml"),
    ],
)
def test_frontend_assets_are_accessible(path: str, content_type: str) -> None:
    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.content


def test_frontend_path_is_independent_of_working_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with TestClient(app) as client:
        response = client.get("/")
        script = client.get("/js/domain.mjs")

    assert response.status_code == 200
    assert script.status_code == 200


def test_api_routes_keep_priority_over_frontend() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        schema = client.get("/openapi.json")
        docs = client.get("/docs")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert schema.status_code == 200
    assert "/ready" in schema.json()["paths"]
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text


def test_unknown_api_path_is_not_frontend_html() -> None:
    with TestClient(app) as client:
        response = client.get("/api/not-implemented")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/app.js", "/js/domain.mjs"])
def test_javascript_mime_does_not_depend_on_os_registry(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows registry entries can override mimetypes' built-in JS mapping.
    mimetypes.init()
    monkeypatch.setitem(mimetypes.types_map, ".js", "text/plain")
    monkeypatch.setitem(mimetypes.types_map, ".mjs", "application/octet-stream")

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/", "/app.js", "/js/domain.mjs"])
def test_frontend_update_ignores_old_cache_validators(path: str) -> None:
    with TestClient(app) as client:
        initial = client.get(path)
        response = client.get(
            path,
            headers={
                "If-None-Match": initial.headers["etag"],
                "If-Modified-Since": initial.headers["last-modified"],
            },
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.content == initial.content


def test_html_has_content_before_javascript_runs() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert 'id="startup-state"' in response.text
    assert "<noscript>" in response.text
    assert "Открываем кабинет" in response.text
