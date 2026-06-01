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
from pathlib import Path
from typing import Any

from zw_brain.capability_registry.runtime import require_surface
from zw_brain.command.runtime import get_service
from zw_brain.shared.auth_context import (
    dev_iam_bypass_auth_context,
    reset_auth_context,
    set_auth_context,
)
from zw_brain.shared.runtime_config import (
    DevBypassInProductionError,
    get_dev_iam_bypass_enabled,
)

TOOLS_DIR = Path(__file__).with_name("tools")


def _invoke_under_dev_identity(name: str, payload: dict[str, Any]) -> Any:
    """Invoke a capability with the dev-bypass AuthContext bound.

    The MCP daemon is gated to start only under dev-IAM-bypass; binding the synthetic
    identity lets the shared C1/N1 boundary resolver enforce role-holding for MCP exactly
    as it does for REST, instead of treating the call as unchecked system-origin.
    """
    token = set_auth_context(dev_iam_bypass_auth_context())
    try:
        return get_service().invoke_skill(name, payload)
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


def call_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_surface(name, "mcp")
    result = _invoke_under_dev_identity(name, payload)
    return {"tool": name, "result": result}


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


def _handle_tools_call(id_: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = (params or {}).get("name", "")
    arguments = (params or {}).get("arguments", {}) or {}
    if not name:
        return _err(id_, -32602, "missing tool name", {"received": params})
    try:
        require_surface(name, "mcp")
    except KeyError:
        return _err(id_, -32601, f"unknown tool: {name}")
    except Exception as e:  # noqa: BLE001 — SurfaceNotEnabledError + others
        return _err(id_, -32601, f"tool unavailable: {name} — {type(e).__name__}: {e}")
    try:
        result = _invoke_under_dev_identity(name, arguments)
    except Exception as e:  # noqa: BLE001
        return _err(id_, -32000, f"{type(e).__name__}: {e}", {"tool": name})
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
            resp = _handle_tools_call(id_, params)
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
