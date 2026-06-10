"""zw-brain MCP runtime.

F6：把 F4 派生的 zw_brain/entry/mcp/tools/*.json (53 个 tool spec) 暴露给
外部 Cursor / Claude 等 MCP client 调用。

设计：
- 不引外部 MCP SDK（避免 162M sdk 依赖；MCP stdio JSON-RPC 协议本身极简）。
- 自实现 stdio JSON-RPC 2.0：每行一条 JSON 消息，处理 3 个核心方法：
    initialize  → 返回 server capabilities
    tools/list  → 返回 53 个 tools 描述符
    tools/call  → dispatch 到 brain.invoke_skill(skill_id, payload)
- 兼容性范围：MCP 2024-11-05 spec 核心 + 必要的 ping。Cursor 默认 stdio。

鉴权（本期实际状态 — dev-only daemon，与 A2A 同模型）：
- 每次 call_tool 绑定 dev-iam-bypass 合成身份（让共享 C1/N1 边界 resolver 对 MCP 面
  和 REST 一样强制 role-holding）；但合成身份「无真实鉴权、持全角色」。
- 因此 serve_stdio 启动门禁镜像 A2A `serve_http`：`get_dev_iam_bypass_enabled()`
  在 `ZW_BRAIN_DEPLOY_MODE in {prod,production}` 下抛 `DevBypassInProductionError`，
  daemon 拒绝以非零退出码启动 → M5「prod fail-closed」不变量在 MCP 面强制（否则
  MCP 面会带全角色 bypass 启动，C1/N1 resolver 成 no-op，伪造 role 永被放行）。

子命令：
    serve [--transport stdio]   stdio JSON-RPC daemon（默认 stdio，启动门禁同上）
    list-tools                  print all tool descriptors (existing)
    call-tool NAME --payload    one-shot invoke (existing)
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from zw_brain.capability_registry.runtime import (
    SurfaceNotEnabledError,
    require_surface,
)
from zw_brain.command.runtime import get_service
from zw_brain.domain.errors import (
    AccessDeniedError,
    ConfirmationRequiredError,
    NotFoundError,
    QuotaExceededError,
    TrustLevelInsufficientError,
)
from zw_brain.shared.auth_context import (
    dev_iam_bypass_auth_context,
    reset_auth_context,
    set_auth_context,
)
from zw_brain.shared.logkit import bind_request_context, reset_request_context, setup_logging
from zw_brain.shared.runtime_config import (
    DevBypassInProductionError,
    get_dev_iam_bypass_enabled,
    get_mcp_caller_trust_level,
    mcp_trust_level_allows_write,
)

TOOLS_DIR = Path(__file__).with_name("tools")

# mcp-hardening S2: every capability invoked through this daemon is attributed to the
# MCP consumer surface in audit_event + capability_call rows.
MCP_SOURCE = "mcp"

# mcp-hardening S4: per-process MCP tool-call quota. A misbehaving Agent that hammers
# tools is throttled at the entry layer (protocol hardening — protects the backend) and
# the over-limit call returns a STRUCTURED quota error with retry_after rather than a
# black-box failure. Window + ceiling are env-tunable; the default ceiling is high enough
# never to affect interactive use. Counter is in-process (the stdio daemon is single-
# process); ``reset_mcp_quota`` lets tests drive the cut deterministically.
_QUOTA_WINDOW_SECONDS = 60
_mcp_call_window: dict[str, list[float]] = {}


def _mcp_quota_limit() -> int:
    import os  # noqa: PLC0415

    raw = (os.environ.get("ZW_BRAIN_MCP_TOOL_QUOTA_PER_MINUTE") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def reset_mcp_quota() -> None:
    """Clear the in-process MCP tool-call window (test hook / daemon restart)."""
    _mcp_call_window.clear()


def _enforce_mcp_quota(name: str) -> None:
    """Sliding-window per-tool call quota (S4). No-op unless the env ceiling is set.

    Raises ``QuotaExceededError`` (with retry_after) when the per-minute ceiling for
    this tool is exceeded; the structured projection happens in the JSON-RPC handler.
    """
    import time  # noqa: PLC0415

    limit = _mcp_quota_limit()
    if limit <= 0:
        return
    now = time.monotonic()
    window = [t for t in _mcp_call_window.get(name, []) if now - t < _QUOTA_WINDOW_SECONDS]
    if len(window) >= limit:
        oldest = min(window)
        retry_after = max(1, int(_QUOTA_WINDOW_SECONDS - (now - oldest)) + 1)
        _mcp_call_window[name] = window
        raise QuotaExceededError(
            f"MCP tool {name} exceeded {limit} calls / {_QUOTA_WINDOW_SECONDS}s",
            retry_after=retry_after,
            scope="mcp_tool_call",
        )
    window.append(now)
    _mcp_call_window[name] = window


def _is_responsibility_bearing(manifest: dict[str, Any]) -> bool:
    """A capability is a responsibility-bearing write when it has side effects or
    requires human confirmation (mcp-hardening S6 / §5.4.5).

    These are exactly the operations an untrusted external Agent must not trigger
    directly through MCP.
    """
    return bool(manifest.get("side_effects")) or bool(manifest.get("human_confirmation_required"))


def _enforce_caller_trust(name: str, manifest: dict[str, Any], *, caller_trust_level: str) -> None:
    """Trust-level cut for the MCP surface (S6).

    Untrusted callers may exercise read / non-responsibility capabilities, but a
    responsibility-bearing write (e.g. application.* approve / delivery mutate) is
    refused with a structured ``trust_level_insufficient`` reason. The rejection is
    audited (reject phase) before raising so the denial is observable.
    """
    if not _is_responsibility_bearing(manifest):
        return
    if mcp_trust_level_allows_write(caller_trust_level):
        return
    _emit_mcp_reject_audit(name, caller_trust_level)
    raise TrustLevelInsufficientError(
        f"MCP caller trust_level={caller_trust_level!r} cannot invoke responsibility-bearing "
        f"capability {name!r}",
        trust_level=caller_trust_level,
    )


def _emit_mcp_reject_audit(name: str, caller_trust_level: str) -> None:
    """Record an audit_event for an MCP trust-level rejection (S6).

    D4 (段 7a): an audit emit failure MUST abort rather than be swallowed — a denial
    that left no audit trail is itself a compliance gap. The daemon always has the
    durable sink configured (``get_service`` wires it on first build), so this emit
    succeeds on every real path; if the sink is genuinely unavailable ``audit_bus.emit``
    raises ``AuditWriteError`` and the call aborts (fail-closed), which is the correct
    D4 outcome for a security-relevant reject.
    """
    import zw_brain.shared.audit as audit_bus  # noqa: PLC0415

    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id=f"mcp-reject:{name}",
            actor=f"mcp:agent:{caller_trust_level}",
            skill_id=name,
            phase="reject",
            payload={
                "source": MCP_SOURCE,
                "decision": "reject",
                "reason": TrustLevelInsufficientError.reason,
                "trust_level": caller_trust_level,
                "audit_class": "read-sensitive",
            },
        )
    )


def _invoke_under_dev_identity(name: str, payload: dict[str, Any]) -> Any:
    """Invoke a capability with the dev-bypass AuthContext bound.

    The MCP daemon is gated to start only under dev-IAM-bypass; binding the synthetic
    identity lets the shared C1/N1 boundary resolver enforce role-holding for MCP exactly
    as it does for REST, instead of treating the call as unchecked system-origin.

    mcp-hardening S2: ``source='mcp'`` is stamped so the audit_event + capability_call
    rows carry the MCP provenance.
    """
    token = set_auth_context(dev_iam_bypass_auth_context())
    try:
        return get_service().invoke_skill(name, payload, source=MCP_SOURCE)
    finally:
        reset_auth_context(token)

# MCP protocol version we implement (anchor for client compatibility checks).
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "zw-brain-mcp"
SERVER_VERSION = "1.0.0"


def list_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        tools.append(json.loads(path.read_text(encoding="utf-8")))
    return tools


def resolve_tool_manifest(name: str, *, caller_trust_level: str | None = None) -> dict[str, Any]:
    """Resolve a live, MCP-exposed manifest + apply the trust-level cut.

    Raises:
      - ``KeyError`` — no such capability registered (→ tool_not_found, S5).
      - ``SurfaceNotEnabledError`` — capability exists but not exposed on MCP or not
        live (→ tool_not_found, S5 exposure filter).
      - ``TrustLevelInsufficientError`` — responsibility-bearing write refused for an
        untrusted caller (→ trust_level_insufficient, S6).
    """
    trust = caller_trust_level if caller_trust_level is not None else get_mcp_caller_trust_level()
    manifest = require_surface(name, "mcp")  # KeyError / SurfaceNotEnabledError
    _enforce_caller_trust(name, manifest, caller_trust_level=trust)
    return manifest


def invoke_tool(
    name: str, payload: dict[str, Any], *, caller_trust_level: str | None = None
) -> dict[str, Any]:
    """Single entry shared by the one-shot CLI and the stdio tools/call handler.

    Applies the S5 exposure gate + S6 trust cut, then invokes under the dev identity
    with ``source='mcp'`` (S2). human_confirmation_required capabilities surface a
    structured ``pending_confirmation`` envelope instead of committing (S3).
    """
    resolve_tool_manifest(name, caller_trust_level=caller_trust_level)
    _enforce_mcp_quota(name)
    try:
        result = _invoke_under_dev_identity(name, payload)
    except ConfirmationRequiredError:
        # S3: do NOT silently swallow / commit — hand the client a structured
        # "待确认" envelope it must re-issue with confirmed=true to commit.
        return {
            "tool": name,
            "status": "pending_confirmation",
            "confirmation_required": True,
            "message": "Requires user confirmation — re-invoke with confirmed=true to commit.",
            "retry_with": {"confirmed": True},
        }
    return {"tool": name, "status": "ok", "result": result}


def call_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_tool(name, payload)


# ─── stdio JSON-RPC ────────────────────────────────────────────────────────

def _ok(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": payload}


def _handle_initialize(id_: Any, params: dict[str, Any]) -> dict[str, Any]:
    client_proto = (params or {}).get("protocolVersion", MCP_PROTOCOL_VERSION)
    return _ok(
        id_,
        {
            "protocolVersion": client_proto,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {"listChanged": False}},
        },
    )


def _handle_tools_list(id_: Any) -> dict[str, Any]:
    return _ok(id_, {"tools": list_tools()})


# mcp-hardening S4 — JSON-RPC error codes for the known, machine-actionable failure
# classes. The IDE/Agent reads ``error.data.reason`` to branch deterministically instead
# of treating every failure as an opaque -32000 / HTTP 500. -326xx are protocol-reserved;
# the application errors use the -320xx server-error band with distinct ``data.reason``.
_RPC_TOOL_NOT_FOUND = -32601  # protocol: method/tool not found (also S5 exposure cut)
_RPC_INVALID_PARAMS = -32602  # protocol: invalid params
_RPC_TRUST_DENIED = -32003    # app: trust_level_insufficient (S6)
_RPC_ACCESS_DENIED = -32004   # app: role / permission / tenant policy denial
_RPC_QUOTA_EXCEEDED = -32005  # app: quota_exceeded (+ retry_after) (S4)
_RPC_NOT_FOUND = -32006       # app: referenced domain entity missing
_RPC_INTERNAL = -32000        # app: unclassified server error (last resort)


def _structured_invocation_error(id_: Any, name: str, exc: Exception) -> dict[str, Any]:
    """Map a known capability-invocation exception to a structured JSON-RPC error (S4).

    Every branch carries ``data.reason`` so the client can dispatch on a stable code;
    quota additionally carries ``retry_after``. Unknown exceptions fall through to a
    classified-as-internal error that still names the type (never a bare black box).
    """
    if isinstance(exc, QuotaExceededError):
        return _err(
            id_, _RPC_QUOTA_EXCEEDED, f"quota exceeded for tool {name}",
            {"tool": name, "reason": "quota_exceeded", "retry_after": exc.retry_after,
             "scope": exc.scope or "mcp_tool_call"},
        )
    if isinstance(exc, TrustLevelInsufficientError):
        # Subclass of AccessDeniedError; checked first so it gets the trust-specific code.
        return _err(
            id_, _RPC_TRUST_DENIED, f"{type(exc).__name__}: {exc}",
            {"tool": name, "reason": exc.reason, "trust_level": exc.trust_level},
        )
    if isinstance(exc, NotFoundError):
        return _err(
            id_, _RPC_NOT_FOUND, f"{type(exc).__name__}: {exc}",
            {"tool": name, "reason": "entity_not_found"},
        )
    if isinstance(exc, AccessDeniedError):
        # Message keeps the type-name prefix so existing consumer-surface assertions
        # (e.g. C1/N1 suite) that branch on 'AccessDenied' still hold; the machine-
        # actionable signal is the stable ``data.reason``.
        return _err(
            id_, _RPC_ACCESS_DENIED, f"{type(exc).__name__}: {exc}",
            {"tool": name, "reason": "access_denied"},
        )
    return _err(
        id_, _RPC_INTERNAL, f"{type(exc).__name__}: {exc}",
        {"tool": name, "reason": "internal_error"},
    )


def _handle_tools_call(id_: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = (params or {}).get("name", "")
    arguments = (params or {}).get("arguments", {}) or {}
    if not name:
        return _err(id_, _RPC_INVALID_PARAMS, "missing tool name", {"received": params})
    # S5 exposure cut: KeyError (no such capability) and SurfaceNotEnabledError
    # (registered but not exposed on MCP / not live) both project to tool_not_found.
    try:
        resolve_tool_manifest(name)
    except (KeyError, SurfaceNotEnabledError):
        return _err(
            id_, _RPC_TOOL_NOT_FOUND, f"tool_not_found: {name}",
            {"tool": name, "reason": "tool_not_found"},
        )
    except TrustLevelInsufficientError as e:  # S6
        return _structured_invocation_error(id_, name, e)
    # S4: entry-layer quota throttle → structured quota_exceeded + retry_after.
    try:
        _enforce_mcp_quota(name)
    except QuotaExceededError as e:
        return _structured_invocation_error(id_, name, e)
    try:
        result = _invoke_under_dev_identity(name, arguments)
    except ConfirmationRequiredError:
        # S3: structured "待确认" — NOT a silent None and NOT a committed write.
        # Surfaced as a successful tools/call result the client can branch on; isError
        # stays False because needing confirmation is a normal, expected protocol turn.
        confirmation = {
            "tool": name,
            "status": "pending_confirmation",
            "confirmation_required": True,
            "message": "Requires user confirmation — re-invoke with confirmed=true to commit.",
            "retry_with": {"confirmed": True},
        }
        return _ok(
            id_,
            {
                "content": [{"type": "text", "text": json.dumps(confirmation, ensure_ascii=False)}],
                "isError": False,
                "structuredContent": confirmation,
            },
        )
    except Exception as e:  # noqa: BLE001 — classified into structured S4 errors
        return _structured_invocation_error(id_, name, e)
    # MCP tools/call 返回 content[] 包装 text；这里把 JSON 结果序列化为 text content
    return _ok(
        id_,
        {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
            ],
            "isError": False,
        },
    )


def serve_stdio() -> int:
    """Read JSON-RPC messages line by line on stdin; write responses on stdout.

    Notifications (no id) get no response. EOF on stdin → exit 0.

    M5 prod guard (mirrors A2A ``serve_http``): every ``tools/call`` binds the
    dev-iam-bypass synthetic identity, which holds all roles with no real
    authentication. If that bypass would leak into a prod deploy mode the shared
    C1/N1 boundary resolver becomes a no-op (a forged role is always honored).
    Evaluate the gate up-front and refuse to start (exit 2) instead of failing
    open — identical to the A2A daemon's start-up gate.
    """
    try:
        get_dev_iam_bypass_enabled()
    except DevBypassInProductionError as exc:
        # 启动期 banner 直写 stderr（不走 logger）：拒启诊断必须在 logging 未配置时也可见
        sys.stderr.write(f"[mcp] refusing to start: {exc}\n")
        return 2
    sys.stderr.write(f"[mcp] {SERVER_NAME} {SERVER_VERSION} stdio ready ({len(list_tools())} tools)\n")
    sys.stderr.flush()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as e:
            resp = _err(None, -32700, f"parse error: {e}")
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        id_ = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}

        if method == "initialize":
            resp = _handle_initialize(id_, params)
        elif method == "initialized" or method == "notifications/initialized":
            # client→server notification, no response
            continue
        elif method == "ping":
            resp = _ok(id_, {})
        elif method == "tools/list":
            resp = _handle_tools_list(id_)
        elif method == "tools/call":
            # request_id 与 JSON-RPC id 关联（含随机后缀防 id 重复），贯穿到日志全链
            tokens = bind_request_context(
                f"mcp-{id_}-{uuid.uuid4().hex[:6]}", entry="mcp"
            )
            try:
                resp = _handle_tools_call(id_, params)
            finally:
                reset_request_context(tokens)
        elif method == "shutdown":
            resp = _ok(id_, None)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            return 0
        else:
            resp = _err(id_, -32601, f"method not found: {method}")

        # notifications (no id) get no response
        if id_ is None:
            continue
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    setup_logging("mcp")
    parser = argparse.ArgumentParser(description="zw-brain MCP runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run stdio JSON-RPC daemon (Cursor/Claude default)")
    serve.add_argument("--transport", choices=["stdio"], default="stdio")

    sub.add_parser("list-tools", help="print all tool descriptors")

    call = sub.add_parser("call-tool", help="one-shot tool invoke")
    call.add_argument("name")
    call.add_argument("--payload", default="{}")

    args = parser.parse_args()

    if args.command == "serve":
        return serve_stdio()

    if args.command == "list-tools":
        print(json.dumps(list_tools(), ensure_ascii=False, indent=2))
        return 0

    payload = json.loads(args.payload)
    print(json.dumps(call_tool(args.name, payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
