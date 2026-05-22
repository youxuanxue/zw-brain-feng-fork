from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import ssl
import time
from collections.abc import Callable
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
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
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.shared.auth_context import auth_context_from_claims, reset_auth_context, set_auth_context
from zw_brain.shared.auth_session import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    AuthSession,
    AuthSessionStore,
)
from zw_brain.shared.iaf_oidc import (
    DEFAULT_IAF_CLIENT_ID,
    HttpRequest,
    HttpResponse,
    IafOidcClient,
    IafOidcError,
    IafOidcStateError,
    IafOidcStateStore,
    IafOidcTokenError,
    IafOidcTokenHealthError,
    verify_iaf_access_token,
)
from zw_brain.shared.runtime_config import (
    get_dev_iam_bypass_enabled,
    get_iaf_insecure_tls_dev_ack,
    get_iaf_verify_ssl,
    get_rest_host,
    get_rest_port,
)
from zw_brain.shared.session_context import build_trusted_skill_payload
from zw_brain.skill_registration.runtime import SurfaceNotEnabledError, require_surface

_LOGGER = logging.getLogger(__name__)
_JWKS_CACHE_TTL_SECONDS = 600
# R-008/R-009: 从单一来源 role_codes 派生（含 admin / system）
from zw_brain.domain.role_codes import ALL_ROLE_CODES as _DEV_IAM_BYPASS_ROLES  # noqa: E402

_DEV_IAM_BYPASS_SUBJECT = "dev-iam-bypass"
_DEV_IAM_BYPASS_USERNAME = "dev_iam_bypass"
_DEV_IAM_BYPASS_DISPLAY_NAME = "开发调试账号（IAM bypass）"


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
_IAF_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_AUTH_SESSION_STORE = AuthSessionStore()


def _iaf_client_id() -> str:
    return (os.environ.get("ZW_BRAIN_IAF_RESOURCE") or os.environ.get("ZW_BRAIN_IAF_CLIENT_ID") or DEFAULT_IAF_CLIENT_ID).strip() or DEFAULT_IAF_CLIENT_ID


def _dev_iam_bypass_user_profile() -> dict[str, Any]:
    from zw_brain.shared.session_context import apply_runtime_context, contexts_from_role_codes

    snapshot = {
        "subject": _DEV_IAM_BYPASS_SUBJECT,
        "username": _DEV_IAM_BYPASS_USERNAME,
        "display_name": _DEV_IAM_BYPASS_DISPLAY_NAME,
        "tenant_id": "sd-default",
        "org_code": "dev",
        "role_codes": list(_DEV_IAM_BYPASS_ROLES),
    }
    contexts = contexts_from_role_codes(snapshot["role_codes"], org_code="dev")
    return apply_runtime_context(snapshot, contexts, preferred_org_code="dev", preferred_role_code="ROLE_ORGAN_OPERATER")


def _dev_iam_bypass_claims() -> dict[str, Any]:
    client_id = _iaf_client_id()
    return {
        "sub": _DEV_IAM_BYPASS_SUBJECT,
        "preferred_username": _DEV_IAM_BYPASS_USERNAME,
        "project_id": "sd-default",
        "org_code": "dev",
        "realm_access": {"roles": ["DEV_IAM_BYPASS"]},
        "resource_access": {client_id: {"roles": list(_DEV_IAM_BYPASS_ROLES)}},
        "development_iam_bypass": True,
    }


def configure_iaf_auth_runtime(
    *,
    transport: Callable[[HttpRequest], HttpResponse] | None = None,
    jwks: dict[str, Any] | None = None,
    state_store: IafOidcStateStore | None = None,
    session_store: AuthSessionStore | None = None,
) -> None:
    global _IAF_TRANSPORT, _IAF_JWKS, _IAF_STATE_STORE, _AUTH_SESSION_STORE
    _IAF_TRANSPORT = transport
    _IAF_JWKS = jwks
    _IAF_JWKS_CACHE.clear()
    if state_store is not None:
        _IAF_STATE_STORE = state_store
    if session_store is not None:
        _AUTH_SESSION_STORE = session_store
    else:
        _AUTH_SESSION_STORE.clear()


def get_auth_session_store() -> AuthSessionStore:
    return _AUTH_SESSION_STORE


def _iaf_ssl_context() -> ssl.SSLContext:
    # ZW_BRAIN_IAF_VERIFY_SSL=false only takes effect when paired with
    # ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only — otherwise the value is silently ignored and
    # a default-verifying context is returned. Prevents a single env typo from disabling TLS in prod.
    if not get_iaf_verify_ssl() and get_iaf_insecure_tls_dev_ack():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    cafile = os.environ.get("ZW_BRAIN_IAF_CA_FILE") or None
    return ssl.create_default_context(cafile=cafile)


def _default_transport(request: HttpRequest) -> HttpResponse:
    url_request = UrlRequest(request.url, data=request.body, headers=request.headers, method=request.method)
    try:
        with urlopen(url_request, timeout=5, context=_iaf_ssl_context()) as response:
            return HttpResponse(status_code=response.status, body=response.read(), headers=dict(response.headers.items()))
    except HTTPError as exc:
        return HttpResponse(status_code=exc.code, body=exc.read(), headers=dict(exc.headers.items()))
    except URLError as exc:
        raise IafOidcError("IAF token endpoint unavailable") from exc


def _fetch_jwks(client: IafOidcClient) -> dict[str, Any]:
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


def _get_jwks(client: IafOidcClient, *, force_refresh: bool = False) -> dict[str, Any]:
    if _IAF_JWKS is not None:
        return _IAF_JWKS
    cache_key = client.config.endpoints.jwks_uri
    cached = _IAF_JWKS_CACHE.get(cache_key)
    now = time.time()
    if not force_refresh and cached is not None and (now - cached[0]) < _JWKS_CACHE_TTL_SECONDS:
        return cached[1]
    payload = _fetch_jwks(client)
    _IAF_JWKS_CACHE[cache_key] = (now, payload)
    return payload


def _verify_access_token_with_refresh(client: IafOidcClient, access_token: str) -> dict[str, Any]:
    # Single-retry on JWKS-key miss so a rotated kid does not require a process restart, and so that
    # signature failures still propagate as IafOidcTokenError rather than being papered over.
    try:
        return verify_iaf_access_token(access_token, config=client.config, jwks=_get_jwks(client))
    except IafOidcTokenError as exc:
        if "jwks key mismatch" in str(exc) and _IAF_JWKS is None:
            return verify_iaf_access_token(access_token, config=client.config, jwks=_get_jwks(client, force_refresh=True))
        raise


class ThreadingRestServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False


class RestHandler(BaseHTTPRequestHandler):
    def _iaf_login_returns_json_envelope(self, qs: dict[str, list[str]]) -> bool:
        """SPA/API expect JSON (authorization_url…); top-level browser navigations use redirects."""
        fmt = str((qs.get("format") or [""])[-1]).strip().lower()
        if fmt == "json":
            return True
        accept_all = self.headers.get("Accept") or ""
        parts = [p.strip() for p in accept_all.split(",") if p.strip()]
        first_mt = parts[0].split(";")[0].strip().lower() if parts else ""
        return first_mt == "application/json"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/auth/iaf/config":
            self._handle_iaf_config()
            return
        if parsed.path == "/auth/iaf/login":
            self._handle_iaf_login(parsed)
            return
        if parsed.path == "/auth/iaf/logout":
            self._handle_iaf_logout(parsed)
            return
        if parsed.path == "/auth/iaf/session":
            self._handle_iaf_session()
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
            self._with_authenticated_request(lambda claims: self._handle_api_snapshot(parsed, claims))
            return
        if parsed.path.startswith("/api/skills/"):
            self._with_authenticated_request(lambda claims: self._handle_api_skill_get(parsed, claims))
            return
        if parsed.path in {"/", "/index.html"}:
            self._serve_file(WEB_ROOT / "index.html")
            return
        if parsed.path.startswith("/css/") or parsed.path.startswith("/js/") or parsed.path.startswith("/assets/"):
            self._serve_file(WEB_ROOT / parsed.path.lstrip("/"), enforce_web_root=True)
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/auth/iaf/token":
            self._handle_iaf_token()
            return
        if parsed.path == "/auth/iaf/refresh":
            self._handle_iaf_refresh()
            return
        if parsed.path == "/auth/iaf/dev-bypass-login":
            self._handle_iaf_dev_bypass_login()
            return
        if parsed.path.startswith("/api/skills/"):
            self._with_authenticated_request(lambda claims: self._handle_api_skill_post(parsed, claims))
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def _handle_iaf_config(self) -> None:
        development_iam_bypass_enabled = get_dev_iam_bypass_enabled()
        body: dict[str, Any] = {
            "configured": True,
            "development_iam_bypass_enabled": development_iam_bypass_enabled,
        }
        if development_iam_bypass_enabled:
            # Frontend reads the bypass user from here instead of fabricating its own claims;
            # keeps server as the single source of truth for the synthetic identity.
            body["development_iam_bypass_user"] = _dev_iam_bypass_user_profile()
        try:
            config = IafOidcClient().config
            body["iaf"] = config.public_dict()
        except IafOidcError as exc:
            body["configured"] = False
            body["detail"] = str(exc)
        self._json(200, body)

    def _handle_iaf_login(self, parsed) -> None:  # type: ignore[no-untyped-def]
        try:
            qs = parse_qs(parsed.query)
            redirect_uri = self._same_origin_url((qs.get("redirect_uri") or [""])[-1], default_path="/")
            login_state = _IAF_STATE_STORE.issue(redirect_uri=redirect_uri)
            auth = IafOidcClient().authorization_request(redirect_uri=redirect_uri, login_state=login_state)
            if self._iaf_login_returns_json_envelope(qs):
                self._json(200, {"authorization_url": auth.url, "state": auth.state, "nonce": auth.nonce})
                return
            self._redirect(auth.url)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_api_snapshot(self, parsed, _claims: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        qs = parse_qs(parsed.query)
        params = {k: v[-1] for k, v in qs.items()}
        session = self._get_cookie_session()
        if session is not None:
            params = self._trusted_skill_payload(session, params)
        else:
            params.setdefault("role", (qs.get("role") or ["ROLE_ORGAN_OPERATER"])[-1])
        self._json(200, get_service().invoke_skill("system.snapshot", params))

    def _handle_api_skill_get(self, parsed, _claims: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        skill_id = parsed.path[len("/api/skills/"):]
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        require_surface(skill_id, "api")
        session = self._get_cookie_session()
        if session is not None:
            params = self._trusted_skill_payload(session, params)
        self._json(200, get_service().invoke_skill(skill_id, params))

    def _handle_api_skill_post(self, parsed, _claims: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        skill_id = parsed.path[len("/api/skills/"):]
        payload = self._read_json_body()
        require_surface(skill_id, "api")
        session = self._get_cookie_session()
        if session is not None:
            payload = self._trusted_skill_payload(session, payload)
        self._json(200, get_service().invoke_skill(skill_id, payload))

    def _trusted_skill_payload(self, session: AuthSession, client_payload: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = dict(session.actor_snapshot)
        if not snapshot.get("available_contexts"):
            snapshot = get_service().enrich_actor_snapshot_for_session(snapshot)
            updated = _AUTH_SESSION_STORE.update_actor_snapshot(session.session_id, snapshot)
            if updated is not None:
                snapshot = dict(updated.actor_snapshot)
        return build_trusted_skill_payload(client_payload, actor_snapshot=snapshot)

    def _with_authenticated_request(self, handler: Callable[[dict[str, Any]], None]) -> None:
        try:
            # Path 1: cookie-bound BFF session is the primary browser surface. Even with the cookie,
            # we re-run validate_access_token_health + RS256 verification per request so a revoked or
            # tampered token cannot ride the session until expiry.
            session = self._get_cookie_session()
            if session is not None:
                if self._method_requires_csrf() and not self._csrf_token_matches(session):
                    self._json(403, {"error": "csrf_token_invalid"})
                    return
                if session.development_iam_bypass:
                    claims = session.claims or _dev_iam_bypass_claims()
                    context_token = set_auth_context(
                        auth_context_from_claims(claims, client_id=_iaf_client_id(), development_iam_bypass=True)
                    )
                else:
                    client = IafOidcClient()
                    authorization = f"Bearer {session.access_token}"
                    client.validate_access_token_health(authorization=authorization, transport=_IAF_TRANSPORT or _default_transport)
                    claims = _verify_access_token_with_refresh(client, session.access_token)
                    context_token = set_auth_context(auth_context_from_claims(claims, client_id=client.config.client_id))
                try:
                    handler(claims)
                finally:
                    reset_auth_context(context_token)
                return

            # Path 2: dev IAM bypass without an established cookie session (CLI / first-request bootstrap).
            if get_dev_iam_bypass_enabled():
                claims = _dev_iam_bypass_claims()
                context_token = set_auth_context(
                    auth_context_from_claims(claims, client_id=_iaf_client_id(), development_iam_bypass=True)
                )
                try:
                    handler(claims)
                finally:
                    reset_auth_context(context_token)
                return

            # Path 3: Authorization Bearer header — preserved for tests / direct API / CLI consumers.
            client = IafOidcClient()
            authorization = self.headers.get("Authorization") or ""
            client.validate_access_token_health(authorization=authorization, transport=_IAF_TRANSPORT or _default_transport)
            access_token = authorization.split(None, 1)[1]
            claims = _verify_access_token_with_refresh(client, access_token)
            context_token = set_auth_context(auth_context_from_claims(claims, client_id=client.config.client_id))
            try:
                handler(claims)
            finally:
                reset_auth_context(context_token)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _method_requires_csrf(self) -> bool:
        return str(self.command or "").upper() in {"POST", "PUT", "PATCH", "DELETE"}

    def _csrf_token_matches(self, session: AuthSession) -> bool:
        provided = self.headers.get(CSRF_HEADER_NAME) or ""
        if not provided or not session.csrf_token:
            return False
        return secrets.compare_digest(str(provided), session.csrf_token)

    def _get_cookie_session(self) -> AuthSession | None:
        session_id = self._read_session_cookie()
        if not session_id:
            return None
        return _AUTH_SESSION_STORE.get(session_id)

    def _read_session_cookie(self) -> str:
        raw = self.headers.get("Cookie") or ""
        if not raw:
            return ""
        try:
            jar: SimpleCookie = SimpleCookie()
            jar.load(raw)
        except Exception:  # noqa: BLE001
            return ""
        morsel = jar.get(SESSION_COOKIE_NAME)
        return morsel.value if morsel else ""

    def _is_https(self) -> bool:
        # Behind a TLS-terminating proxy the X-Forwarded-Proto header is the authoritative signal.
        return (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"

    def _handle_iaf_token(self) -> None:
        try:
            payload = self._read_json_body()
            code = str(payload.get("code") or "")
            state = str(payload.get("state") or "")
            login_state = _IAF_STATE_STORE.consume(state)
            redirect_uri = login_state.redirect_uri or self._request_url("/")
            client = IafOidcClient()
            token_payload = client.exchange_authorization_code(code=code, redirect_uri=redirect_uri, transport=_IAF_TRANSPORT or _default_transport)
            if not str(token_payload.get("access_token") or ""):
                raise IafOidcTokenError("token response missing access_token")
            claims = self._claims_from_token_payload(client, token_payload, expected_nonce=login_state.nonce)
            actor_result = self._sync_actor_from_claims(claims)
            actor_snapshot = get_service().enrich_actor_snapshot_for_session(actor_result["result"]["actor_snapshots"][0])
            audit_id = str(actor_result.get("audit_id") or "")
            session = _AUTH_SESSION_STORE.create(
                token_payload=token_payload,
                claims=claims,
                actor_snapshot=actor_snapshot,
                audit_id=audit_id,
            )
            self._respond_with_session(session)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_iaf_session(self) -> None:
        # Read-only: returns the public payload (incl. csrf_token) for the session bound to the
        # cookie. Lets a freshly opened tab discover its csrf_token without re-running the OAuth
        # flow — the cookie already carries authentication, sessionStorage is per-tab and needs
        # bootstrapping. 401 if no cookie or session expired; never creates a session.
        try:
            session = self._get_cookie_session()
            if session is None:
                self._json(401, {"error": "session_missing"})
                return
            payload = json.dumps(session.public_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_iaf_dev_bypass_login(self) -> None:
        try:
            if not get_dev_iam_bypass_enabled():
                # 404 mirrors the response for unknown routes so a production server doesn't reveal
                # that this dev-only endpoint exists at all.
                self._json(404, {"error": "not_found", "path": "/auth/iaf/dev-bypass-login"})
                return
            claims = _dev_iam_bypass_claims()
            # Bypass mode skips actor.projection.sync — the synthetic identity is not a real user and
            # has no IAM-issued exp / iat. The session still carries enough actor info for the WebUI.
            actor_snapshot = _dev_iam_bypass_user_profile()
            token_payload = {"access_token": "", "expires_in": 24 * 60 * 60, "refresh_expires_in": 24 * 60 * 60}
            session = _AUTH_SESSION_STORE.create(
                token_payload=token_payload,
                claims=claims,
                actor_snapshot=actor_snapshot,
                audit_id="dev-iam-bypass",
                development_iam_bypass=True,
            )
            self._respond_with_session(session)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _respond_with_session(self, session: AuthSession) -> None:
        payload = json.dumps(session.public_payload(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._send_session_cookie(session)
        self.end_headers()
        self.wfile.write(payload)

    def _send_session_cookie(self, session: AuthSession) -> None:
        max_age = max(int(session.refresh_expires_at - time.time()), 1)
        # SameSite=Lax suffices: state-changing methods additionally require X-CSRF-Token.
        # Secure is set whenever the request looks HTTPS (X-Forwarded-Proto=https) — local plain-HTTP
        # tests still get a Cookie they can replay.
        parts = [
            f"{SESSION_COOKIE_NAME}={session.session_id}",
            "Path=/",
            f"Max-Age={max_age}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self._is_https():
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def _clear_session_cookie(self) -> None:
        parts = [
            f"{SESSION_COOKIE_NAME}=",
            "Path=/",
            "Max-Age=0",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self._is_https():
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def _claims_from_token_payload(self, client: IafOidcClient, token_payload: dict[str, Any], *, expected_nonce: str | None) -> dict[str, Any]:
        id_token = str(token_payload.get("id_token") or "")
        if id_token:
            jwks = _get_jwks(client)
            try:
                return client.verify_id_token(id_token, jwks=jwks, expected_nonce=expected_nonce)
            except IafOidcTokenError as exc:
                if "jwks key mismatch" in str(exc) and _IAF_JWKS is None:
                    return client.verify_id_token(id_token, jwks=_get_jwks(client, force_refresh=True), expected_nonce=expected_nonce)
                raise
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise IafOidcTokenError("token response missing access_token")
        # No id_token in response → still verify the access token signature locally before trusting claims.
        client.validate_access_token_health(authorization=f"Bearer {access_token}", transport=_IAF_TRANSPORT or _default_transport)
        return _verify_access_token_with_refresh(client, access_token)

    def _handle_iaf_refresh(self) -> None:
        try:
            session = self._get_cookie_session()
            if session is None:
                self._json(401, {"error": "session_missing"})
                return
            if not self._csrf_token_matches(session):
                self._json(403, {"error": "csrf_token_invalid"})
                return
            if session.development_iam_bypass:
                # Bypass sessions carry no IAM refresh token; "refresh" simply echoes current payload.
                self._respond_with_session(session)
                return
            if not session.refresh_token:
                self._json(401, {"error": "refresh_token_missing"})
                return
            client = IafOidcClient()
            token_payload = client.refresh_access_token(refresh_token=session.refresh_token, transport=_IAF_TRANSPORT or _default_transport)
            claims = session.claims
            if str(token_payload.get("id_token") or ""):
                # Re-verify claims when IAM rotates the id_token during refresh.
                claims = self._claims_from_token_payload(client, token_payload, expected_nonce=None)
            updated = _AUTH_SESSION_STORE.update_tokens(session.session_id, token_payload=token_payload, claims=claims)
            if updated is None:
                self._json(401, {"error": "session_expired"})
                return
            self._respond_with_session(updated)
        except IafOidcError as exc:
            if "HTTP 401" in str(exc):
                self._json(401, {"error": "iaf_auth_error", "detail": "refresh token invalid or expired"})
                return
            self._handle_error(exc)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _sync_actor_from_claims(self, claims: dict[str, Any]) -> dict[str, Any]:
        # IAM-initiated first-login projection is a system-origin write, not a ROLE_BUSIAUDIT user action;
        # using role="system" keeps the audit/capability_call actor honest. The "system" role is granted
        # exactly the actor.projection.sync.execute permission in zw_brain/domain/policy.py.
        return get_service().invoke_skill(
            "actor.projection.sync",
            {
                "iaf_claims": claims,
                "tenant_id": str(claims.get("project_id") or "sd-default"),
                "org_code": claims.get("org_code"),
                "role": "system",
                "confirmed": True,
            },
        )

    def _handle_iaf_logout(self, parsed) -> None:  # type: ignore[no-untyped-def]
        try:
            qs = parse_qs(parsed.query)
            redirect_uri = (qs.get("redirect_uri") or [""])[-1]
            session = self._get_cookie_session()
            id_token_hint = session.id_token if session is not None else ""
            if session is not None:
                _AUTH_SESSION_STORE.delete(session.session_id)
            if get_dev_iam_bypass_enabled() or (session is not None and session.development_iam_bypass):
                self._respond_with_logout({"logout_url": self._same_origin_url(redirect_uri, default_path="/"), "local_auth_cleared": True})
                return
            config = IafOidcClient().config
            params: dict[str, str] = {}
            if redirect_uri:
                params["post_logout_redirect_uri"] = self._same_origin_url(redirect_uri, default_path="/")
            if id_token_hint:
                params["id_token_hint"] = id_token_hint
            logout_url = config.endpoints.logout_endpoint
            if params:
                logout_url = f"{logout_url}?{urlencode(params)}"
            self._respond_with_logout({"logout_url": logout_url, "local_auth_cleared": True})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _respond_with_logout(self, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._clear_session_cookie()
        self.end_headers()
        self.wfile.write(payload)

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
        if isinstance(exc, (AccessDeniedError, DomainAccessDeniedError)):
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
        if isinstance(exc, IafOidcTokenHealthError):
            self._json(exc.status_code, {"error": "iaf_token_health_error", "detail": str(exc)})
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

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _empty(self, status: int, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def log_iaf_runtime_warnings() -> None:
    if get_dev_iam_bypass_enabled():
        _LOGGER.warning(
            "ZW_BRAIN_DEV_IAM_BYPASS=1 is active — IAM auth is fully bypassed and every "
            "request runs as a synthetic %s user with all 6 ROLE_* roles. DEVELOPMENT ONLY.",
            _DEV_IAM_BYPASS_SUBJECT,
        )
    elif os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS", "").strip() == "1":
        _LOGGER.warning(
            "ZW_BRAIN_DEV_IAM_BYPASS=1 is set but ZW_BRAIN_DEV_IAM_BYPASS_ACK is missing/invalid; "
            "bypass is IGNORED. Set ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only to enable it."
        )
    if not get_iaf_verify_ssl() and get_iaf_insecure_tls_dev_ack():
        _LOGGER.warning("ZW_BRAIN_IAF_VERIFY_SSL=false with dev ack — IAM TLS verification is OFF. DEVELOPMENT ONLY.")
    elif not get_iaf_verify_ssl():
        _LOGGER.warning(
            "ZW_BRAIN_IAF_VERIFY_SSL=false is set but ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK is missing/invalid; "
            "TLS verification stays ON. Set ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only to disable."
        )


def main(host: str | None = None, port: int | None = None) -> None:
    log_iaf_runtime_warnings()
    ThreadingRestServer((host or get_rest_host(), port or get_rest_port()), RestHandler).serve_forever()


if __name__ == "__main__":
    main()
