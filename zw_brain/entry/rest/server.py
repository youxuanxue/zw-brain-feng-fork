from __future__ import annotations

import html
import json
import mimetypes
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from zw_brain.command.brain import (
    AccessDeniedError,
    BrainServiceError,
    ConfirmationRequiredError,
    InvalidStateError,
    NotFoundError,
    UnknownSkillError,
)
from zw_brain.command.runtime import get_service
from zw_brain.shared.iaf_oidc import (
    HttpRequest,
    HttpResponse,
    IafOidcClient,
    IafOidcError,
    IafOidcStateError,
    IafOidcStateStore,
    IafOidcTokenError,
)
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
_IAF_STATE_STORE = IafOidcStateStore()
_IAF_TRANSPORT: Callable[[HttpRequest], HttpResponse] | None = None
_IAF_JWKS: dict[str, Any] | None = None


def configure_iaf_auth_runtime(
    *,
    transport: Callable[[HttpRequest], HttpResponse] | None = None,
    jwks: dict[str, Any] | None = None,
    state_store: IafOidcStateStore | None = None,
) -> None:
    global _IAF_TRANSPORT, _IAF_JWKS, _IAF_STATE_STORE
    _IAF_TRANSPORT = transport
    _IAF_JWKS = jwks
    if state_store is not None:
        _IAF_STATE_STORE = state_store


def _default_transport(request: HttpRequest) -> HttpResponse:
    url_request = UrlRequest(request.url, data=request.body, headers=request.headers, method=request.method)
    try:
        with urlopen(url_request, timeout=5) as response:
            return HttpResponse(status_code=response.status, body=response.read(), headers=dict(response.headers.items()))
    except HTTPError as exc:
        return HttpResponse(status_code=exc.code, body=exc.read(), headers=dict(exc.headers.items()))
    except URLError as exc:
        raise IafOidcError("IAF token endpoint unavailable") from exc


def _default_jwks(client: IafOidcClient) -> dict[str, Any]:
    request = HttpRequest(method="GET", url=client.config.endpoints.jwks_uri, headers={"Accept": "application/json"}, body=b"")
    response = (_IAF_TRANSPORT or _default_transport)(request)
    if response.status_code < 200 or response.status_code >= 300:
        raise IafOidcError(f"JWKS fetch failed with HTTP {response.status_code}")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except Exception as exc:
        raise IafOidcError("JWKS fetch returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise IafOidcError("JWKS fetch returned invalid payload")
    return payload


class RestHandler(BaseHTTPRequestHandler):
    def _prefer_iaf_callback_html_document(self, qs: dict[str, list[str]]) -> bool:
        """Browser top-level OAuth redirects send Sec-Fetch-Dest: document / text/html; APIs use format=json / application/json."""
        fmt = str((qs.get("format") or [""])[-1]).strip().lower()
        if fmt == "json":
            return False
        dest = (self.headers.get("Sec-Fetch-Dest") or "").strip().lower()
        if dest == "document":
            return True
        accept_all = self.headers.get("Accept") or ""
        parts = [p.strip() for p in accept_all.split(",") if p.strip()]
        first_mt = parts[0].split(";")[0].strip().lower() if parts else ""
        if first_mt == "application/json":
            return False
        if "text/html" in accept_all.lower():
            return True
        return False

    def _html_iaf_login_complete_reload(self, *, spa_path: str = "/") -> None:
        target_js = json.dumps(spa_path, ensure_ascii=False)
        escaped_href = html.escape(spa_path, quote=True)
        doc = (
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"/>"
            f"<meta http-equiv=\"refresh\" content=\"0;url={escaped_href}\"/>"
            "<title>IAF IAM 登录</title></head><body>"
            "<p>授权已完成，正在返回政务数据大脑…</p>"
            f"<script>location.replace({target_js});</script>"
            f"<noscript><a href=\"{escaped_href}\">点击进入应用</a></noscript>"
            "</body></html>"
        )
        payload = doc.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/auth/iaf/login":
            self._handle_iaf_login(parsed)
            return
        if parsed.path == "/auth/iaf/callback":
            self._handle_iaf_callback(parsed)
            return
        if parsed.path == "/auth/iaf/logout":
            self._handle_iaf_logout(parsed)
            return
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "service": "zw-brain-rest"})
            return
        if parsed.path == "/openapi.json":
            self._serve_file(OPENAPI_PATH)
            return
        if parsed.path == "/favicon.ico":
            self._empty(204, "image/x-icon")
            return
        if parsed.path == "/api/snapshot":
            qs = parse_qs(parsed.query)
            role = (qs.get("role") or ["r1"])[-1]
            self._json(200, get_service().invoke_skill("system.snapshot", {"role": role}))
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
            self._serve_file(WEB_ROOT / parsed.path.lstrip("/"), enforce_web_root=True)
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

    def _handle_iaf_login(self, parsed) -> None:  # type: ignore[no-untyped-def]
        try:
            qs = parse_qs(parsed.query)
            redirect_uri = self._same_origin_url((qs.get("redirect_uri") or [""])[-1], default_path="/auth/iaf/callback")
            login_state = _IAF_STATE_STORE.issue(redirect_uri=redirect_uri)
            auth = IafOidcClient().authorization_request(redirect_uri=redirect_uri, login_state=login_state)
            self._json(200, {"authorization_url": auth.url, "state": auth.state, "nonce": auth.nonce})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_iaf_callback(self, parsed) -> None:  # type: ignore[no-untyped-def]
        try:
            qs = parse_qs(parsed.query)
            code = (qs.get("code") or [""])[-1]
            login_state = _IAF_STATE_STORE.consume((qs.get("state") or [""])[-1])
            redirect_uri = login_state.redirect_uri or self._request_url("/auth/iaf/callback")
            client = IafOidcClient()
            token_payload = client.exchange_authorization_code(code=code, redirect_uri=redirect_uri, transport=_IAF_TRANSPORT or _default_transport)
            id_token = str(token_payload.get("id_token") or "")
            jwks = _IAF_JWKS or _default_jwks(client)
            claims = client.verify_id_token(id_token, jwks=jwks, expected_nonce=login_state.nonce)
            actor_result = get_service().invoke_skill(
                "actor.projection.sync",
                {
                    "iaf_claims": claims,
                    "tenant_id": str(claims.get("project_id") or "sd-default"),
                    "org_code": claims.get("org_code"),
                    "role": "r7",
                    "confirmed": True,
                },
            )
            if self._prefer_iaf_callback_html_document(qs):
                self._html_iaf_login_complete_reload(spa_path="/?iaf_login=done")
                return
            self._json(
                200,
                {
                    "authenticated": True,
                    "actor_snapshot": actor_result["result"]["actor_snapshots"][0],
                    "audit_id": actor_result["audit_id"],
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_iaf_logout(self, parsed) -> None:  # type: ignore[no-untyped-def]
        try:
            qs = parse_qs(parsed.query)
            config = IafOidcClient().config
            params = {}
            redirect_uri = (qs.get("post_logout_redirect_uri") or [""])[-1]
            if redirect_uri:
                params["post_logout_redirect_uri"] = self._same_origin_url(redirect_uri, default_path="/")
            logout_url = config.endpoints.logout_endpoint
            if params:
                logout_url = f"{logout_url}?{urlencode(params)}"
            self._json(200, {"logout_url": logout_url, "local_auth_cleared": True})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _request_url(self, path: str) -> str:
        scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        host = self.headers.get("Host") or f"{get_rest_host()}:{get_rest_port()}"
        return f"{scheme}://{host}{path}"

    def _same_origin_url(self, candidate: str, *, default_path: str) -> str:
        fallback = self._request_url(default_path)
        if not candidate:
            return fallback
        current = urlparse(fallback)
        parsed = urlparse(candidate)
        if parsed.scheme and parsed.netloc:
            if parsed.scheme != current.scheme or parsed.netloc != current.netloc:
                raise IafOidcStateError("redirect origin mismatch")
            return candidate
        path = parsed.path or default_path
        if not path.startswith("/"):
            raise IafOidcStateError("redirect path invalid")
        return urlunparse((current.scheme, current.netloc, path, "", parsed.query, parsed.fragment))

    def _serve_file(self, path: Path, *, enforce_web_root: bool = False) -> None:
        if enforce_web_root:
            try:
                path.resolve().relative_to(WEB_ROOT.resolve())
            except (ValueError, FileNotFoundError):
                self._json(404, {"error": "not_found", "path": str(path)})
                return
        if not path.exists() or not path.is_file():
            self._json(404, {"error": "not_found", "path": str(path)})
            return
        payload = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        try:
            _ = path.resolve().relative_to(WEB_ROOT.resolve())
        except ValueError:
            pass
        else:
            suf = path.suffix.lower()
            if suf in {".js", ".css"} or path.name.lower() == "index.html":
                self.send_header("Cache-Control", "no-cache")
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
        if isinstance(exc, NotFoundError):
            self._json(422, {"error": "entity_not_found", "detail": str(exc)})
            return
        if isinstance(exc, UnknownSkillError):
            self._json(404, {"error": exc.__class__.__name__, "detail": str(exc)})
            return
        if isinstance(exc, InvalidStateError):
            self._json(409, {"error": "invalid_state", "detail": str(exc)})
            return
        if isinstance(exc, IafOidcStateError):
            self._json(400, {"error": "iaf_state_error", "detail": str(exc)})
            return
        if isinstance(exc, IafOidcTokenError):
            self._json(401, {"error": "iaf_auth_error", "detail": str(exc)})
            return
        if isinstance(exc, IafOidcError):
            detail = str(exc).replace("token exchange", "authorization exchange")
            self._json(400, {"error": "iaf_auth_error", "detail": detail})
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

    def _empty(self, status: int, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def main(host: str | None = None, port: int | None = None) -> None:
    HTTPServer((host or get_rest_host(), port or get_rest_port()), RestHandler).serve_forever()


if __name__ == "__main__":
    main()
