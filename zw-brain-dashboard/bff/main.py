"""Backend-for-Frontend gateway for zw-brain-dashboard (Phase-0 placeholder).

Per design baseline D15 + D19:
  - The BFF MUST be read-only (it forwards `GET /api/skills/dashboard.*` to
    the brain's read-only Skill endpoints). Any handler that introduces a
    write verb (POST/PUT/PATCH/DELETE) will be flagged by
    scripts/check_dashboard_readonly.py.
  - Web framework choice (FastAPI vs Hono vs Flask vs alternatives) is
    deferred to Phase-0 PoC. Phase-0 ships a stdlib http.server stub so the
    skeleton imports without optional deps.

The handler intentionally uses `do_GET` only (no `do_POST` / `do_PUT` /
`do_DELETE`) — that's the mechanical guarantee, not just a comment.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


class DashboardBffHandler(BaseHTTPRequestHandler):
    """Phase-0 read-only BFF handler."""

    def do_GET(self) -> None:  # noqa: N802 — http.server contract
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._respond(200, {"status": "ok", "phase": "0", "writable": False})
            return
        if parsed.path.startswith("/api/skills/dashboard."):
            skill_id = parsed.path[len("/api/skills/") :]
            self._respond(
                200,
                {
                    "skill_id": skill_id,
                    "result": None,
                    "note": "Phase-0 placeholder — wire to brain read-only Skill endpoint",
                },
            )
            return
        self._respond(404, {"error": "not_found", "path": parsed.path})

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def main(host: str = "127.0.0.1", port: int = 8801) -> None:
    HTTPServer((host, port), DashboardBffHandler).serve_forever()


if __name__ == "__main__":
    main()
