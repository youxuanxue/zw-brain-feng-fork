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
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from urllib.request import Request as UrlRequest

from zw_brain.capability_registry.runtime import SurfaceNotEnabledError, require_surface
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
from zw_brain.domain.repositories.governance_projection import ActorMatchError
from zw_brain.shared.auth_context import auth_context_from_claims, reset_auth_context, set_auth_context
from zw_brain.shared.auth_session import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    AuthSession,
    AuthSessionStoreProtocol,
    create_auth_session_store,
    validate_session_store_for_deploy,
)
from zw_brain.shared.http_security import SERVER_BANNER, security_headers
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
from zw_brain.shared.logkit import (
    bind_request_context,
    get_request_id,
    reset_request_context,
    set_log_actor,
    setup_logging,
)
from zw_brain.shared.runtime_config import (
    DevBypassInProductionError,
    InsecureIafTlsInProductionError,
    get_dev_iam_bypass_enabled,
    get_dev_iam_bypass_role_codes,
    get_iaf_insecure_tls_dev_ack,
    get_iaf_insecure_tls_enabled,
    get_iaf_verify_ssl,
    get_rest_host,
    get_rest_port,
)
from zw_brain.shared.session_context import build_trusted_skill_payload

_LOGGER = logging.getLogger(__name__)
_ACCESS_LOGGER = logging.getLogger("zw_brain.entry.rest.access")
_JWKS_CACHE_TTL_SECONDS = 600


def _agent_runtime_bridge():
    """延迟加载 AgentRuntime 桥接模块，避免未安装 agent-runtime 时阻塞 REST 启动。"""
    from zw_brain.command import agent_runtime_bridge as bridge

    return bridge
# R-008/R-009: 从单一来源 role_codes 派生（含 admin / system）
from zw_brain.domain.role_codes import ALL_ROLE_CODES as _DEV_IAM_BYPASS_ROLES_DEFAULT  # noqa: E402

_DEV_IAM_BYPASS_SUBJECT = "dev-iam-bypass"
_DEV_IAM_BYPASS_USERNAME = "dev_iam_bypass"
_DEV_IAM_BYPASS_DISPLAY_NAME = "本地调试"


def _dev_iam_bypass_role_codes() -> list[str]:
    """Resolve the role list for dev-iam-bypass (delegates to the shared SoT).

    `ZW_BRAIN_DEV_IAM_BYPASS_ROLES` overrides the default ALL_ROLE_CODES so the
    无产品岗位 (A3) and 单一岗位 acceptance scenarios are reproducible without
    spinning up a real IAM. The canonical implementation now lives in
    ``shared.runtime_config.get_dev_iam_bypass_role_codes`` so REST / MCP / A2A / CLI
    all build the identical dev-bypass AuthContext (C1/N1 boundary uniformity).
    """
    return get_dev_iam_bypass_role_codes()


def _web_root() -> Path:
    package_root = Path(__file__).resolve().parents[2]
    repo_root = package_root.parents[0]
    repo_path = repo_root / "zw-brain-web"
    if repo_path.exists():
        return repo_path
    packaged_path = package_root / "_assets" / "zw-brain-web"
    return packaged_path


def _web_public_root(web_root: Path | None = None) -> Path:
    """Serve Vite production bundle when dist-vite/ exists; else dev index (needs Vite :5173)."""
    root = web_root or _web_root()
    built = root / "dist-vite"
    if (built / "index.html").is_file():
        return built
    return root


WEB_ROOT = _web_root()
WEB_PUBLIC_ROOT = _web_public_root(WEB_ROOT)
OPENAPI_PATH = Path(__file__).with_name("openapi.json")
_IAF_STATE_STORE = IafOidcStateStore()

# 反向代理可在 /zw-brain 下挂载本服务（前端 vite base 同值）。后端前缀单一事实源在此，
# 路由前统一剥前缀；前端从 import.meta.env.BASE_URL 派生，禁止各处硬编码字面量。
APP_PATH_PREFIX = "/zw-brain"
# 前缀部署下 SPA 入口与登录/登出回落路径。
APP_DEFAULT_PATH = f"{APP_PATH_PREFIX}/"


def _strip_app_prefix(path: str) -> str:
    """剥掉 APP_PATH_PREFIX 前缀；仅命中精确前缀或其下子路径，避免 /zw-brainfoo 被误剥。"""
    if path == APP_PATH_PREFIX:
        return "/"
    if path.startswith(f"{APP_PATH_PREFIX}/"):
        return path[len(APP_PATH_PREFIX):]
    return path
_IAF_TRANSPORT: Callable[[HttpRequest], HttpResponse] | None = None
_IAF_JWKS: dict[str, Any] | None = None
_IAF_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_AUTH_SESSION_STORE: AuthSessionStoreProtocol = create_auth_session_store()


def _iaf_client_id() -> str:
    return (os.environ.get("ZW_BRAIN_IAF_RESOURCE") or os.environ.get("ZW_BRAIN_IAF_CLIENT_ID") or DEFAULT_IAF_CLIENT_ID).strip() or DEFAULT_IAF_CLIENT_ID


def _dev_iam_bypass_org_code() -> str:
    """dev-bypass 会话所属机构码（仅 dev 档生效）。

    默认 'dev'；可经 ZW_BRAIN_DEV_IAM_BYPASS_ORG 指为真实机构码（如省大数据局
    11370000MB284651XL），使带 R11 方向 guard 的动作（有条件二级部门审核
    application.dept_approve）在 dev 走查 / e2e 中可走通——guard 对 owner_org_code
    fail-closed，会话 org 须与资源提供方一致才放行（与真 IAM 会话同语义，不开后门）。
    """
    return (os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS_ORG") or "dev").strip() or "dev"


def _dev_iam_bypass_user_profile() -> dict[str, Any]:
    from zw_brain.shared.session_context import apply_runtime_context, contexts_from_role_codes

    role_codes = _dev_iam_bypass_role_codes()
    org_code = _dev_iam_bypass_org_code()
    snapshot = {
        "subject": _DEV_IAM_BYPASS_SUBJECT,
        "username": _DEV_IAM_BYPASS_USERNAME,
        "display_name": _DEV_IAM_BYPASS_DISPLAY_NAME,
        "tenant_id": "sd-default",
        "org_code": org_code,
        "role_codes": role_codes,
    }
    contexts = contexts_from_role_codes(role_codes, org_code=org_code)
    preferred_role = "ROLE_ORGAN_OPERATER" if "ROLE_ORGAN_OPERATER" in role_codes else (role_codes[0] if role_codes else None)
    return apply_runtime_context(snapshot, contexts, preferred_org_code=org_code, preferred_role_code=preferred_role)


def _dev_iam_bypass_claims() -> dict[str, Any]:
    client_id = _iaf_client_id()
    return {
        "sub": _DEV_IAM_BYPASS_SUBJECT,
        "preferred_username": _DEV_IAM_BYPASS_USERNAME,
        "project_id": "sd-default",
        "org_code": _dev_iam_bypass_org_code(),
        "realm_access": {"roles": ["DEV_IAM_BYPASS"]},
        "resource_access": {client_id: {"roles": _dev_iam_bypass_role_codes()}},
        "development_iam_bypass": True,
    }


def configure_iaf_auth_runtime(
    *,
    transport: Callable[[HttpRequest], HttpResponse] | None = None,
    jwks: dict[str, Any] | None = None,
    state_store: IafOidcStateStore | None = None,
    session_store: AuthSessionStoreProtocol | None = None,
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


def get_auth_session_store() -> AuthSessionStoreProtocol:
    return _AUTH_SESSION_STORE


def _iaf_ssl_context() -> ssl.SSLContext:
    # ZW_BRAIN_IAF_VERIFY_SSL=false only takes effect when paired with
    # ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only — otherwise the value is silently ignored and
    # a default-verifying context is returned. Prevents a single env typo from disabling TLS in prod.
    # M5 fail-closed: get_iaf_insecure_tls_enabled() raises InsecureIafTlsInProductionError if that
    # combination would leak into a prod deploy mode (caught at startup in main()).
    if get_iaf_insecure_tls_enabled():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    cafile = os.environ.get("ZW_BRAIN_IAF_CA_FILE") or None
    return ssl.create_default_context(cafile=cafile)


def _iaf_http_opener():
    # Ambient http(s)_proxy breaks internal IAM URLs in many dev containers; IAF calls bypass proxy.
    return build_opener(ProxyHandler({}), HTTPSHandler(context=_iaf_ssl_context()))


def _default_transport(request: HttpRequest) -> HttpResponse:
    url_request = UrlRequest(request.url, data=request.body, headers=request.headers, method=request.method)
    try:
        with _iaf_http_opener().open(url_request, timeout=10) as response:
            return HttpResponse(status_code=response.status, body=response.read(), headers=dict(response.headers.items()))
    except HTTPError as exc:
        return HttpResponse(status_code=exc.code, body=exc.read(), headers=dict(exc.headers.items()))
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise IafOidcError(f"IAF token endpoint unavailable ({request.url}): {reason}") from exc


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
    def handle_one_request(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler hook
        # 客户端在服务端写响应途中提前断开（浏览器取消请求 / 刷新 / 关页）会让 socket 写抛
        # BrokenPipeError / ConnectionResetError，默认会被 socketserver 当未捕获异常打 traceback
        # 到 stderr，污染日志。在请求边界**一处**收口，覆盖所有写路径（_json/_serve_file/_redirect/
        # _empty/_respond_*），断开即静默关连接——比逐方法 try 完整且更简洁。
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True  # client gone — drop quietly, no traceback

    def version_string(self) -> str:  # noqa: N802 — BaseHTTPRequestHandler hook
        # 去版本化 Server banner：stdlib 默认回 "BaseHTTP/x.y Python/a.b.c" 泄漏 Python 版本，
        # 扫描器据此匹配 Python DoS / Server type 发现。只暴露产品名。
        return SERVER_BANNER

    def end_headers(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler hook
        # 唯一的响应头收口点：所有写路径（_json/_serve_file/_redirect/_empty/会话/登出，
        # 以及 stdlib send_error 的 501/400 错误页）都经此 flush，故安全头一处注入即全覆盖。
        for header, value in security_headers(is_https=self._is_https()):
            self.send_header(header, value)
        request_id = get_request_id()
        if request_id:
            self.send_header("X-Request-Id", request_id)
        super().end_headers()

    def send_response(self, code: int, message: str | None = None) -> None:  # noqa: N802
        self._response_status = code  # captured for the access log
        super().send_response(code, message)

    def _iaf_login_returns_json_envelope(self, qs: dict[str, list[str]]) -> bool:
        """SPA/API expect JSON (authorization_url…); top-level browser navigations use redirects."""
        fmt = str((qs.get("format") or [""])[-1]).strip().lower()
        if fmt == "json":
            return True
        accept_all = self.headers.get("Accept") or ""
        parts = [p.strip() for p in accept_all.split(",") if p.strip()]
        first_mt = parts[0].split(";")[0].strip().lower() if parts else ""
        return first_mt == "application/json"

    _STATIC_PREFIXES = ("/css/", "/js/", "/assets/", "/src/")

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch_logged("GET", self._route_get)

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch_logged("POST", self._route_post)

    def _dispatch_logged(self, method: str, route: Callable[[], None]) -> None:
        """每请求日志边界：bind request_id（接收或生成）→ 路由 → access log → token reset。

        ThreadingMixIn 下 keep-alive 连接会复用线程，finally 处的 reset 保证上下文
        不跨请求串味（与 auth_context 同款 token 纪律）。
        """
        path = _strip_app_prefix(urlparse(self.path).path)
        tokens = bind_request_context(self.headers.get("X-Request-Id"), entry="rest")
        self._response_status = 0
        started = time.monotonic()
        try:
            route()
        finally:
            quiet = path.startswith(self._STATIC_PREFIXES) or path == "/favicon.ico"
            _ACCESS_LOGGER.log(
                logging.DEBUG if quiet else logging.INFO,
                "%s %s -> %s",
                method,
                path,
                self._response_status,
                extra={
                    "event": "http_access",
                    "method": method,
                    "path": path,
                    "status": self._response_status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                },
            )
            reset_request_context(tokens)

    def _route_get(self) -> None:
        parsed = urlparse(self.path)
        path = _strip_app_prefix(parsed.path)

        if path == "/auth/iaf/config":
            self._handle_iaf_config()
            return
        if path == "/auth/iaf/login":
            self._handle_iaf_login(parsed)
            return
        if path == "/auth/iaf/logout":
            self._handle_iaf_logout(parsed)
            return
        if path == "/auth/iaf/session":
            self._handle_iaf_session()
            return
        if path == "/health":
            body: dict[str, Any] = {"status": "ok", "service": "zw-brain-rest"}
            body["agent_runtime"] = _agent_runtime_bridge().runtime_status()
            self._json(200, body)
            return
        if path == "/api/agent-runtime/agents":
            self._with_authenticated_request(lambda claims: self._handle_agent_runtime_agents(claims))
            return
        if path == "/api/agent-runtime/status":
            self._json(200, _agent_runtime_bridge().runtime_status())
            return
        # 非阻塞任务轮询：GET /api/agent-runtime/tasks/{task_id}（排除 /resume 后缀）
        if path.startswith("/api/agent-runtime/tasks/") and not path.endswith("/resume"):
            # 注意：先匹配 /api/agent-runtime/tasks/{task_id}，避免与 POST /api/agent-runtime/tasks 冲突
            self._with_authenticated_request(lambda claims: self._handle_agent_runtime_task_get(path, claims))
            return
        if path == "/openapi.json":
            self._serve_file(OPENAPI_PATH)
            return
        if path == "/favicon.ico":
            self._empty(204, "image/x-icon")
            return
        if path == "/api/snapshot":
            self._with_authenticated_request(lambda claims: self._handle_api_snapshot(parsed, claims))
            return
        if path.startswith("/api/skills/"):
            self._with_authenticated_request(lambda claims: self._handle_api_skill_get(parsed, claims))
            return
        if path in {"/", "/index.html"}:
            self._serve_file(WEB_PUBLIC_ROOT / "index.html")
            return
        if (
            path.startswith("/css/")
            or path.startswith("/js/")
            or path.startswith("/assets/")
            or path.startswith("/src/")
        ):
            rel = path.lstrip("/")
            # Dev index references /src/*.ts — only resolvable from source tree, not dist-vite.
            serve_root = WEB_ROOT if rel.startswith("src/") else WEB_PUBLIC_ROOT
            self._serve_file(serve_root / rel, enforce_web_root=True)
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def _route_post(self) -> None:
        parsed = urlparse(self.path)
        path = _strip_app_prefix(parsed.path)

        if path == "/api/client-logs":
            # 前端错误上报：无鉴权（boot/登录前失败也要可上报），防刷与落日志逻辑
            # 收在 client_logs 模块；绝不写业务库（段 25）。
            self._handle_client_logs()
            return
        if path == "/auth/iaf/token":
            self._handle_iaf_token()
            return
        if path == "/auth/iaf/refresh":
            self._handle_iaf_refresh()
            return
        if path == "/auth/iaf/dev-bypass-login":
            self._handle_iaf_dev_bypass_login()
            return
        if path.startswith("/api/skills/"):
            self._with_authenticated_request(lambda claims: self._handle_api_skill_post(parsed, claims))
            return
        if path == "/api/agent-runtime/tasks":
            self._with_authenticated_request(lambda claims: self._handle_agent_runtime_task_post(parsed, claims))
            return
        # Resume task: POST /api/agent-runtime/tasks/{task_id}/resume
        if path.startswith("/api/agent-runtime/tasks/") and path.endswith("/resume"):
            self._with_authenticated_request(lambda claims: self._handle_agent_runtime_task_resume(path, claims))
            return
        self.close_connection = True  # POST body 未消费，防 keep-alive 残留字节毒化下一请求
        self._json(404, {"error": "not_found", "path": parsed.path})

    def _handle_agent_runtime_agents(self, _claims: dict[str, Any]) -> None:
        try:
            self._json(200, {"agents": _agent_runtime_bridge().list_builtin_agents()})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_agent_runtime_task_post(self, parsed: Any, claims: dict[str, Any]) -> None:
        """POST /api/agent-runtime/tasks — 启动 Agent 任务。

        默认使用非阻塞模式（立即返回 task_id, status=pending），
        客户端通过 GET /api/agent-runtime/tasks/{task_id} 轮询结果。
        若查询参数 ?mode=block 则使用阻塞模式（等待任务完成）。
        """
        bridge = _agent_runtime_bridge()
        try:
            payload = self._read_json_body()
            agent_id = str(payload.get("agent_id") or "").strip()
            user_input = str(payload.get("input") or "").strip()
            if not agent_id or not user_input:
                self._json(400, {"error": "agent_id and input are required"})
                return

            session = self._get_cookie_session()
            requested_role = str(payload.get("role") or "")
            if session is not None:
                trusted = self._trusted_skill_payload(session, payload)
                role = str(trusted.get("role") or "")
                payload = trusted
            else:
                role = self._role_from_verified_identity(requested_role)
            if not role:
                self._json(403, {"error": "no_product_role_for_identity"})
                return

            task_metadata = {
                k: v
                for k, v in payload.items()
                if k not in {"agent_id", "input", "role"}
            }
            qs = parse_qs(parsed.query)
            mode = (qs.get("mode") or [""])[-1].strip().lower()

            if mode == "block":
                # 阻塞模式：等待任务完成（兼容旧客户端）
                result = bridge.start_agent_task(
                    brain=get_service(),
                    role=role,
                    agent_id=agent_id,
                    user_input=user_input,
                    request_id=str(payload.get("request_id") or "") or None,
                    metadata=task_metadata,
                )
            else:
                # 非阻塞模式（默认）：立即返回 task_id，客户端轮询
                result = bridge.start_agent_task_background(
                    brain=get_service(),
                    role=role,
                    agent_id=agent_id,
                    user_input=user_input,
                    request_id=str(payload.get("request_id") or "") or None,
                    metadata=task_metadata,
                )
            self._json(200, result)
        except bridge.AgentRuntimeNotEnabledError as exc:
            self._json(503, {"error": "agent_runtime_disabled", "detail": str(exc)})
        except bridge.AgentRuntimeNotFoundError as exc:
            self._json(404, {"error": "agent_not_found", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_agent_runtime_task_get(self, path: str, _claims: dict[str, Any]) -> None:
        """GET /api/agent-runtime/tasks/{task_id} — 轮询非阻塞任务状态。"""
        bridge = _agent_runtime_bridge()
        # 提取 task_id: path = "/api/agent-runtime/tasks/{task_id}"
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[-2] != "tasks" or parts[0] != "api":
            self._json(400, {"error": "invalid_task_path", "detail": f"expected /api/agent-runtime/tasks/<task_id>, got {path}"})
            return
        task_id = parts[-1]
        if not task_id:
            self._json(400, {"error": "task_id_required"})
            return

        try:
            result = bridge.poll_agent_task(task_id)
            self._json(200, result)
        except bridge.AgentRuntimeNotFoundError as exc:
            self._json(404, {"error": "task_not_found", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

    def _handle_agent_runtime_task_resume(self, path: str, _claims: dict[str, Any]) -> None:
        """POST /api/agent-runtime/tasks/{task_id}/resume — 恢复等待中的 Agent 任务。"""
        bridge = _agent_runtime_bridge()
        # 提取 task_id: path = "/api/agent-runtime/tasks/{task_id}/resume"
        base = path.strip("/")
        # Remove the "/resume" suffix
        if not base.endswith("/resume"):
            self._json(400, {"error": "invalid_resume_path", "detail": f"expected .../tasks/<task_id>/resume, got {path}"})
            return
        task_path = base[:-7]  # strip "/resume"
        parts = task_path.split("/")
        if len(parts) != 4 or parts[-2] != "tasks" or parts[0] != "api":
            self._json(400, {"error": "invalid_resume_path", "detail": f"expected .../tasks/<task_id>/resume, got {path}"})
            return
        task_id = parts[-1]
        if not task_id:
            self._json(400, {"error": "task_id_required"})
            return

        try:
            payload = self._read_json_body()
            input_data = payload.get("input")
            if input_data is None:
                self._json(400, {"error": "input_required", "detail": "resume payload must contain 'input'"})
                return
            result = bridge.resume_agent_task(
                task_id=task_id,
                input_data=input_data,
            )
            self._json(200, result)
        except bridge.AgentRuntimeNotEnabledError as exc:
            self._json(503, {"error": "agent_runtime_disabled", "detail": str(exc)})
        except bridge.AgentRuntimeNotFoundError as exc:
            self._json(404, {"error": "task_not_found", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._handle_error(exc)

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
            redirect_uri = self._same_origin_url((qs.get("redirect_uri") or [""])[-1], default_path=APP_DEFAULT_PATH)
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
            # No cookie session (bearer / dev-bypass): the authorization role MUST come
            # from the verified identity, never a client-supplied ?role= — otherwise a
            # low-privilege token holder could claim a role they don't hold. C1 fix.
            params = self._apply_verified_identity_role(params)
        self._json(200, get_service().invoke_skill("system.snapshot", params))

    def _handle_api_skill_get(self, parsed, _claims: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        skill_id = _strip_app_prefix(parsed.path)[len("/api/skills/"):]
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        require_surface(skill_id, "api")
        session = self._get_cookie_session()
        if session is not None:
            params = self._trusted_skill_payload(session, params)
        else:
            # C1 fix: bearer / dev-bypass GET reads must derive role from the verified
            # identity, never the client-supplied ?role=. Without this, a low-privilege
            # token holder could read SECURITY_AUDIT-only capabilities (e.g.
            # audit.event.query) by omitting / spoofing the role query param.
            params = self._apply_verified_identity_role(params)
        self._json(200, get_service().invoke_skill(skill_id, params))

    def _handle_api_skill_post(self, parsed, _claims: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        skill_id = _strip_app_prefix(parsed.path)[len("/api/skills/"):]
        payload = self._read_json_body()
        require_surface(skill_id, "api")
        session = self._get_cookie_session()
        if session is not None:
            payload = self._trusted_skill_payload(session, payload)
        else:
            # C1 fix: bearer / dev-bypass POST must derive role from the verified identity,
            # never a client-supplied "role" in the body (which would let a low-privilege
            # token claim ROLE_SYSTEM and run privileged write capabilities).
            # N1 fix: a POST may target a *write* (side_effects) capability; pass skill_id
            # so a forged write role is NOT silently degraded but surfaced to the shared
            # boundary resolver (brain._resolve_role → IdentityRoleForbiddenError → 403).
            if not isinstance(payload, dict):
                # M7 fix: non-dict JSON body (list/str/int) reaches _apply_verified_identity_role
                # which calls .get → AttributeError → 500. A2A/CLI already return 400 here; REST
                # must too. (GET params are always a dict, so this guard lives on the POST path.)
                self._json(400, {"error": "bad_request", "detail": "request body must be a JSON object"})
                return
            payload = self._apply_verified_identity_role(payload, skill_id=skill_id)
        self._json(200, get_service().invoke_skill(skill_id, payload))

    def _apply_verified_identity_role(self, payload: dict[str, Any], *, skill_id: str | None = None) -> dict[str, Any]:
        """Stamp the identity-derived authorization role into a no-cookie-session payload.

        C1 fix. For bearer-token / dev-bypass requests (no BFF cookie session), the
        authorization role is derived from the verified auth context — NOT trusted from
        the client. A client-supplied ``role`` is honored only when the verified identity
        actually holds it (``_role_from_verified_identity`` enforces that); otherwise the
        identity's first product role is used. If the identity holds no product role the
        request is rejected with 403 instead of silently falling back to a default role.

        N1 fix. For a *write* capability (``side_effects`` declared in its manifest) the
        forged-role case is NOT degraded here: the requested role is preserved and handed
        to the shared boundary resolver (``brain._resolve_role`` →
        ``resolve_role_from_identity``), which denies acting as an unheld role on a write
        (forged actor / corrupt audit attribution). Reads keep least-privilege degrade.

        The dev-IAM-bypass synthetic user holds all role codes, so its derived role
        equals any (valid) requested role — A2A/MCP daemons and local CLI keep working.
        """
        requested_role = str(payload.get("role") or "")
        if skill_id is not None and self._capability_has_side_effects(skill_id):
            # Write path: don't pre-resolve/degrade. Require the identity to hold *some*
            # product role (else 403), then let the shared resolver enforce the held-role
            # rule against the requested write role.
            if not self._role_from_verified_identity(""):
                raise AccessDeniedError("no_product_role_for_identity")
            stamped = dict(payload)
            stamped["role"] = requested_role
            return stamped
        role = self._role_from_verified_identity(requested_role)
        if not role:
            # 403 via _handle_error mapping — identity authenticated but holds no product role.
            raise AccessDeniedError("no_product_role_for_identity")
        stamped = dict(payload)
        # Overwrite (never trust) the client-supplied role with the identity-derived one.
        stamped["role"] = role
        return stamped

    @staticmethod
    def _capability_has_side_effects(skill_id: str) -> bool:
        # skill_id param name is the D33 API-surface envelope key (matches invoke_skill);
        # the helper itself is capability-named per D33 internal-naming rule.
        from zw_brain.capability_registry.runtime import get_manifest
        try:
            return bool((get_manifest(skill_id) or {}).get("side_effects"))
        except KeyError:
            return False

    def _role_from_verified_identity(self, requested_role: str) -> str:
        """Resolve an authorization role from the verified auth context (not the request body).

        Returns the requested role only when the token's claims actually grant it; otherwise
        falls back to the first product role the identity holds, or "" if it holds none.
        """
        from zw_brain.domain.policy import filter_product_role_codes
        from zw_brain.shared.auth_context import get_auth_context

        ctx = get_auth_context()
        allowed = filter_product_role_codes(list(ctx.role_codes)) if ctx is not None else []
        if requested_role and requested_role in allowed:
            return requested_role
        return allowed[0] if allowed else ""

    def _trusted_skill_payload(self, session: AuthSession, client_payload: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = dict(session.actor_snapshot)
        if not snapshot.get("available_contexts"):
            snapshot = get_service().enrich_actor_snapshot_for_session(snapshot)
            updated = _AUTH_SESSION_STORE.update_actor_snapshot(session.session_id, snapshot)
            if updated is not None:
                snapshot = dict(updated.actor_snapshot)
        return build_trusted_skill_payload(client_payload, actor_snapshot=snapshot)

    def _bind_auth(
        self, claims: dict[str, Any], *, client_id: str, development_iam_bypass: bool = False
    ):
        """建立 AuthContext 并把已验证身份回填进日志上下文（actor 随 request context 一起 reset）。"""
        context = auth_context_from_claims(
            claims, client_id=client_id, development_iam_bypass=development_iam_bypass
        )
        set_log_actor(context.username)
        return set_auth_context(context)

    def _with_authenticated_request(self, handler: Callable[[dict[str, Any]], None]) -> None:
        try:
            # Path 1: cookie-bound BFF session is the primary browser surface. Even with the cookie,
            # we re-run validate_access_token_health + RS256 verification per request so a revoked or
            # tampered token cannot ride the session until expiry.
            session = self._get_cookie_session()
            if session is not None:
                if self._method_requires_csrf() and not self._csrf_token_matches(session):
                    self.close_connection = True  # body 未消费，防 keep-alive 残留字节毒化下一请求
                    self._json(403, {"error": "csrf_token_invalid"})
                    return
                if session.development_iam_bypass:
                    claims = session.claims or _dev_iam_bypass_claims()
                    context_token = self._bind_auth(
                        claims, client_id=_iaf_client_id(), development_iam_bypass=True
                    )
                else:
                    client = IafOidcClient()
                    authorization = f"Bearer {session.access_token}"
                    client.validate_access_token_health(authorization=authorization, transport=_IAF_TRANSPORT or _default_transport)
                    claims = _verify_access_token_with_refresh(client, session.access_token)
                    context_token = self._bind_auth(claims, client_id=client.config.client_id)
                try:
                    handler(claims)
                finally:
                    reset_auth_context(context_token)
                return

            # Path 2: dev IAM bypass without an established cookie session (CLI / first-request bootstrap).
            if get_dev_iam_bypass_enabled():
                claims = _dev_iam_bypass_claims()
                context_token = self._bind_auth(
                    claims, client_id=_iaf_client_id(), development_iam_bypass=True
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
            context_token = self._bind_auth(claims, client_id=client.config.client_id)
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
        # Null-safe: end_headers() injects security headers on the malformed-request 400 path too,
        # where stdlib calls end_headers before self.headers is parsed (AttributeError otherwise).
        headers = getattr(self, "headers", None)
        return ((headers.get("X-Forwarded-Proto") if headers else "") or "").lower() == "https"

    def _handle_iaf_token(self) -> None:
        try:
            payload = self._read_json_body()
            code = str(payload.get("code") or "")
            state = str(payload.get("state") or "")
            # Peek first: transient IAF failures must not burn the state so the browser can retry.
            login_state = _IAF_STATE_STORE.get(state)
            redirect_uri = login_state.redirect_uri or self._request_url("/")
            client = IafOidcClient()
            token_payload = client.exchange_authorization_code(code=code, redirect_uri=redirect_uri, transport=_IAF_TRANSPORT or _default_transport)
            # IAF success means the authz code is now burned at IAF — any later failure cannot be
            # retried with the same state/code, so discard immediately to minimize the stale-state window.
            _IAF_STATE_STORE.discard(state)
            if not str(token_payload.get("access_token") or ""):
                raise IafOidcTokenError("token response missing access_token")
            claims = self._claims_from_token_payload(client, token_payload, expected_nonce=login_state.nonce)
            actor_result = self._sync_actor_from_claims(claims)
            # M7 fix: actor.projection.sync can legitimately return an empty actor_snapshots list
            # (e.g. an IAM identity that projects to no product actor). Indexing [0] blindly →
            # IndexError → 500. Treat "authenticated but no projected actor" as 403, not a crash.
            snapshots = ((actor_result or {}).get("result") or {}).get("actor_snapshots") or []
            if not snapshots:
                self._json(403, {"error": "no_product_role_for_identity"})
                return
            actor_snapshot = get_service().enrich_actor_snapshot_for_session(snapshots[0])
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
        # mark_system_origin: this runs while the request AuthContext holds the *user's* identity
        # (which does not personally hold "system"); the in-process system-origin sentinel exempts it
        # from the verified-identity role boundary (C1/N1) without weakening it for client calls.
        from zw_brain.shared.auth_context import mark_system_origin
        return get_service().invoke_skill(
            "actor.projection.sync",
            mark_system_origin({
                "iaf_claims": claims,
                "tenant_id": str(claims.get("project_id") or "sd-default"),
                "org_code": claims.get("org_code"),
                "role": "system",
                "confirmed": True,
            }),
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
                self._respond_with_logout({"logout_url": self._same_origin_url(redirect_uri, default_path=APP_DEFAULT_PATH), "local_auth_cleared": True})
                return
            config = IafOidcClient().config
            params: dict[str, str] = {"client_id": config.client_id}
            if redirect_uri:
                params["post_logout_redirect_uri"] = self._same_origin_url(redirect_uri, default_path=APP_DEFAULT_PATH)
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
        # 优先使用 X-Forwarded-Proto 和 X-Forwarded-Host（nginx 代理时）
        forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").lower()
        scheme = forwarded_proto if forwarded_proto in ("http", "https") else "http"
        # X-Forwarded-Host 可能包含端口，如 "aip.inspurcloud.cn:9443"
        forwarded_host = self.headers.get("X-Forwarded-Host")
        if forwarded_host:
            host = forwarded_host
        else:
            # 从 Host header 获取，可能没有端口
            host = self.headers.get("Host") or f"{get_rest_host()}:{get_rest_port()}"
            # 尝试从 X-Forwarded-Port 获取端口
            forwarded_port = self.headers.get("X-Forwarded-Port")
            if forwarded_port and ":" not in host:
                host = f"{host}:{forwarded_port}"
        return f"{scheme}://{host}{path}"

    def _same_origin_url(self, candidate: str, *, default_path: str) -> str:
        fallback = self._request_url(default_path)
        if not candidate:
            return fallback
        current = urlparse(fallback)
        parsed = urlparse(candidate)
        if parsed.scheme and parsed.netloc:
            # 精确比对 scheme+netloc(host:port)。nginx 反代下外部端口经 _request_url 的
            # X-Forwarded-Host/Port 还原进 current.netloc，故合法回路仍精确相等；
            # 不放宽端口——同 host 异端口可能是攻击者可控的旁路服务（开放重定向风险）。
            if parsed.scheme != current.scheme or parsed.netloc != current.netloc:
                raise IafOidcStateError("redirect origin mismatch")
            return candidate
        path = parsed.path or default_path
        if not path.startswith("/"):
            raise IafOidcStateError("redirect path invalid")
        return urlunparse((current.scheme, current.netloc, path, "", parsed.query, parsed.fragment))

    def _serve_file(self, path: Path, *, enforce_web_root: bool = False) -> None:
        try:
            if enforce_web_root:
                try:
                    resolved = path.resolve()
                    for root in (WEB_ROOT.resolve(), WEB_PUBLIC_ROOT.resolve()):
                        try:
                            resolved.relative_to(root)
                            break
                        except ValueError:
                            continue
                    else:
                        raise ValueError("outside web roots")
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
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected — nothing to do

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def _handle_client_logs(self) -> None:
        from zw_brain.entry.rest.client_logs import MAX_BODY_BYTES, handle_client_log_payload

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > MAX_BODY_BYTES:
            # 不读超限体直接拒——避免无鉴权端点被灌大包；body 未消费，必须断连
            # 否则 keep-alive 复用时残留字节会毒化下一请求的解析
            self.close_connection = True
            self._json(413, {"error": "payload_too_large"})
            return
        raw = self.rfile.read(length) if length > 0 else b""
        status, body = handle_client_log_payload(
            raw,
            remote=str(self.client_address[0]) if self.client_address else "",
            user_agent=self.headers.get("User-Agent", ""),
        )
        if status == 204:
            self._empty(204, "application/json")
            return
        self._json(status, body)

    # 下方 isinstance 链已映射的"预期内拒绝"类型——只记一行 INFO；其余是未预期异常，
    # 落完整堆栈（exception）。日志只加在顶部，映射体与客户端响应保持逐字不变。
    _EXPECTED_REQUEST_ERRORS = (
        SurfaceNotEnabledError,
        DomainAccessDeniedError,
        ActorMatchError,
        IafOidcError,
        BrainServiceError,
    )

    def _handle_error(self, exc: Exception) -> None:
        path = _strip_app_prefix(urlparse(self.path).path)
        if isinstance(exc, self._EXPECTED_REQUEST_ERRORS):
            _LOGGER.info(
                "request rejected: %s: %s",
                exc.__class__.__name__,
                exc,
                extra={"event": "request_rejected", "method": self.command, "path": path},
            )
        else:
            _LOGGER.exception(
                "unhandled error on %s %s",
                self.command,
                path,
                extra={"event": "unhandled_error", "method": self.command, "path": path},
            )
        if isinstance(exc, SurfaceNotEnabledError):
            self._json(404, {"error": "surface_not_enabled", "detail": str(exc)})
            return
        if isinstance(exc, (AccessDeniedError, DomainAccessDeniedError)):
            self._json(403, {"error": "access_denied", "detail": str(exc)})
            return
        if isinstance(exc, ActorMatchError):
            # First IAM login matched more than one claimable legacy actor — fail closed rather
            # than auto-claim the wrong identity. Clean 403, never a 500; no claims PII in body.
            self._json(403, {"error": "actor_identity_ambiguous", "detail": str(exc)})
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
        try:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected — nothing to do

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
        codes = _dev_iam_bypass_role_codes()
        if not codes:
            granted = "no product roles (ZW_BRAIN_DEV_IAM_BYPASS_ROLES=\"\")"
        elif len(codes) == len(_DEV_IAM_BYPASS_ROLES_DEFAULT):
            granted = f"all {len(codes)} ROLE_* roles"
        else:
            granted = f"{len(codes)} role(s): {','.join(codes)}"
        _LOGGER.warning(
            "ZW_BRAIN_DEV_IAM_BYPASS=1 is active — IAM auth is fully bypassed and every "
            "request runs as a synthetic %s user with %s. DEVELOPMENT ONLY.",
            _DEV_IAM_BYPASS_SUBJECT,
            granted,
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
    setup_logging("rest")
    validate_session_store_for_deploy()
    # M5: fail-closed at startup if a dev safety-bypass env leaks into a prod deploy mode.
    # get_dev_iam_bypass_enabled() raises DevBypassInProductionError (auth fully open) and
    # get_iaf_insecure_tls_enabled() raises InsecureIafTlsInProductionError (IAM TLS verification
    # off → MITM surface). Surface either as a clean non-zero exit (refuse to boot) rather than
    # running with a production safety guard silently disabled.
    try:
        get_dev_iam_bypass_enabled()
        get_iaf_insecure_tls_enabled()
    except (DevBypassInProductionError, InsecureIafTlsInProductionError) as exc:
        raise SystemExit(str(exc)) from exc
    log_iaf_runtime_warnings()
    # H2: bring up the in-process blockchain-anchor worker as part of the service
    # lifecycle so the durable anchor_outbox table is drained into audit_receipt.
    # Env-gated (ZW_BRAIN_ANCHOR_WORKER) and auto-off under pytest; the test
    # harness constructs ThreadingRestServer directly and never reaches here.
    from zw_brain.background_tasks import start_anchor_worker, stop_anchor_worker  # noqa: PLC0415

    start_anchor_worker()
    server = ThreadingRestServer((host or get_rest_host(), port or get_rest_port()), RestHandler)
    try:
        server.serve_forever()
    finally:
        stop_anchor_worker()
        server.server_close()


if __name__ == "__main__":
    main()
