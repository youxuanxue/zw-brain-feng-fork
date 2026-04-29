from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from zw_brain.command.brain import BrainServiceError, ConfirmationRequiredError, InvalidStateError, NotFoundError, UnknownSkillError
from zw_brain.command.runtime import get_service
from zw_brain.shared.runtime_config import get_dashboard_bff_host, get_dashboard_bff_port
from zw_brain.skill_registration.runtime import SurfaceNotEnabledError, require_surface


def _dashboard_root() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    repo_root = package_root.parents[0]
    repo_path = repo_root / "zw-brain-dashboard"
    if repo_path.exists():
        return repo_path
    packaged_path = package_root / "_assets" / "zw-brain-dashboard"
    return packaged_path


DASHBOARD_ROOT = _dashboard_root()


class DashboardBffHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — http.server contract
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._respond(200, {"status": "ok", "writable": False})
            return
        if parsed.path.startswith("/api/skills/dashboard."):
            skill_id = parsed.path[len("/api/skills/") :]
            try:
                require_surface(skill_id, "webui")
                result = get_service().invoke_skill(skill_id, {})
                self._respond(200, result)
            except Exception as exc:  # noqa: BLE001
                self._handle_error(exc)
            return
        if parsed.path in {"/", "/index.html"}:
            self._serve_file(DASHBOARD_ROOT / "index.html")
            return
        if parsed.path.startswith("/src/"):
            self._serve_file(DASHBOARD_ROOT / parsed.path.lstrip("/"))
            return
        self._respond(404, {"error": "not_found", "path": parsed.path})

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._respond(404, {"error": "not_found", "path": str(path)})
            return
        payload = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, SurfaceNotEnabledError):
            self._respond(404, {"error": "surface_not_enabled", "detail": str(exc)})
            return
        if isinstance(exc, ConfirmationRequiredError):
            self._respond(409, {"error": "confirmation_required", "detail": str(exc)})
            return
        if isinstance(exc, (UnknownSkillError, NotFoundError)):
            self._respond(404, {"error": exc.__class__.__name__, "detail": str(exc)})
            return
        if isinstance(exc, InvalidStateError):
            self._respond(409, {"error": "invalid_state", "detail": str(exc)})
            return
        if isinstance(exc, BrainServiceError):
            self._respond(400, {"error": exc.__class__.__name__, "detail": str(exc)})
            return
        self._respond(500, {"error": exc.__class__.__name__, "detail": str(exc)})

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def main(host: str | None = None, port: int | None = None) -> None:
    HTTPServer((host or get_dashboard_bff_host(), port or get_dashboard_bff_port()), DashboardBffHandler).serve_forever()


__all__ = ["DashboardBffHandler", "main"]
