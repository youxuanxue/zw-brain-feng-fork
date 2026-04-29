from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from zw_brain.command.brain import AccessDeniedError, BrainServiceError, ConfirmationRequiredError, InvalidStateError, NotFoundError, UnknownSkillError
from zw_brain.command.runtime import get_service
from zw_brain.shared.runtime_config import get_rest_host, get_rest_port
from zw_brain.skill_registration.runtime import SurfaceNotEnabledError, require_surface


def _web_root() -> Path:
    package_root = Path(__file__).resolve().parents[2]
    repo_root = package_root.parents[0]
    repo_path = repo_root / "zw-brain-web"
    if repo_path.exists():
        return repo_path
    packaged_path = package_root / "_assets" / "zw-brain-web"
    return packaged_path


WEB_ROOT = _web_root()
OPENAPI_PATH = Path(__file__).with_name("openapi.json")


class RestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "service": "zw-brain-rest"})
            return
        if parsed.path == "/openapi.json":
            self._serve_file(OPENAPI_PATH)
            return
        if parsed.path == "/api/snapshot":
            self._json(200, get_service().invoke_skill("system.snapshot", {}))
            return
        if parsed.path.startswith("/api/skills/"):
            skill_id = parsed.path[len("/api/skills/"):]
            params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            try:
                require_surface(skill_id, "api")
                self._json(200, get_service().invoke_skill(skill_id, params))
            except Exception as exc:  # noqa: BLE001
                self._handle_error(exc)
            return
        if parsed.path in {"/", "/index.html"}:
            self._serve_file(WEB_ROOT / "index.html")
            return
        if parsed.path.startswith("/css/") or parsed.path.startswith("/js/"):
            self._serve_file(WEB_ROOT / parsed.path.lstrip("/"))
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/skills/"):
            skill_id = parsed.path[len("/api/skills/"):]
            try:
                payload = self._read_json_body()
                require_surface(skill_id, "api")
                self._json(200, get_service().invoke_skill(skill_id, payload))
            except Exception as exc:  # noqa: BLE001
                self._handle_error(exc)
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._json(404, {"error": "not_found", "path": str(path)})
            return
        payload = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, SurfaceNotEnabledError):
            self._json(404, {"error": "surface_not_enabled", "detail": str(exc)})
            return
        if isinstance(exc, AccessDeniedError):
            self._json(403, {"error": "access_denied", "detail": str(exc)})
            return
        if isinstance(exc, ConfirmationRequiredError):
            self._json(409, {"error": "confirmation_required", "skill_id": str(exc)})
            return
        if isinstance(exc, (NotFoundError, UnknownSkillError)):
            self._json(404, {"error": exc.__class__.__name__, "detail": str(exc)})
            return
        if isinstance(exc, InvalidStateError):
            self._json(409, {"error": "invalid_state", "detail": str(exc)})
            return
        if isinstance(exc, BrainServiceError):
            self._json(400, {"error": exc.__class__.__name__, "detail": str(exc)})
            return
        self._json(500, {"error": exc.__class__.__name__, "detail": str(exc)})

    def _json(self, status: int, body: dict | list) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def main(host: str | None = None, port: int | None = None) -> None:
    HTTPServer((host or get_rest_host(), port or get_rest_port()), RestHandler).serve_forever()


if __name__ == "__main__":
    main()
