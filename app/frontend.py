"""Predictable frontend delivery for local development, including Windows."""

from pathlib import Path

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendFiles(StaticFiles):
    media_types = {
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        suffix = Path(path).suffix.lower()
        media_type = self.media_types.get(suffix)
        if path in ("", "."):
            media_type = self.media_types[".html"]
        if media_type:
            response.headers["Content-Type"] = media_type
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def is_not_modified(
        self, response_headers: Headers, request_headers: Headers
    ) -> bool:
        # Re-send files even when an old browser cache sends its validators.
        # These small, unversioned demo assets must update together.
        return False
