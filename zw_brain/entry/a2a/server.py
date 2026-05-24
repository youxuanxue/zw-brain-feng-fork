"""zw-brain A2A runtime.

F6：A2A protocol 行业暂无统一标准。本期实现：
- GET /.well-known/agent.json → 暴露 F4 派生的 agent_card.json
- GET /a2a/skills                  → 列 159 个 skill name+description（discovery）
- GET /a2a/skills/<skill_id>       → 单 skill 的 input schema + roles（runtime_bindings 切片）
- POST /a2a/skills/<skill_id>/invoke → dispatch 到 brain.invoke_skill

鉴权（本期实际状态 — dev-only daemon）：
- daemon 必须在 `ZW_BRAIN_DEV_IAM_BYPASS=1` + `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`
  环境下启动；缺任一 → `serve` 拒绝启动（exit 2），避免无鉴权下被生产配置误拉起。
- 进程内不再校验 cookie/CSRF：daemon 启动门禁等价于「dev workstation + 开发者已显式 ACK」，
  所有调用按 dev-iam-bypass 用户身份走 brain.invoke_skill。
- 生产对接：放 reverse proxy 同域下、上游补 cookie + CSRF 双重提交（同 REST 模型）；
  生产模式落地后此 daemon 应升级为「读 cookie 内 session」或退役独立端口转回 REST sub-router。
独立端口（默认 8801），避免与 REST :8800 冲突。

子命令：
    serve [--host 0.0.0.0] [--port 8801]   HTTP daemon（必须带 IAM bypass + ACK）
    agent-card                              print card (existing)
    invoke SKILL --payload JSON             one-shot (existing)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from zw_brain.command.runtime import get_service
from zw_brain.shared.runtime_config import get_dev_iam_bypass_enabled
from zw_brain.skill_registration.runtime import require_surface

CARD_PATH = Path(__file__).with_name("agent_card.json")
BINDINGS_PATH = Path(__file__).with_name("tools") / "runtime_bindings.json"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8801


def get_agent_card() -> dict[str, Any]:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def get_runtime_bindings() -> list[dict[str, Any]]:
    return json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))


def invoke(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_surface(skill_id, "a2a")
    result = get_service().invoke_skill(skill_id, payload)
    return {"skill_id": skill_id, "result": result}


# ─── HTTP daemon ────────────────────────────────────────────────────────────


def _build_binding_index() -> dict[str, dict[str, Any]]:
    return {item["tool_name"]: item for item in get_runtime_bindings()}


class _A2AHandler(BaseHTTPRequestHandler):
    binding_index: dict[str, dict[str, Any]] = {}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # quieter default log
        self.server.log_file.write(f"[a2a] {format % args}\n")  # type: ignore[attr-defined]
        self.server.log_file.flush()  # type: ignore[attr-defined]

    def _json(self, code: int, body: Any) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON body: {e}") from e

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/.well-known/agent.json", "/a2a/agent_card"):
            self._json(200, get_agent_card())
            return
        if path == "/a2a/skills":
            self._json(200, [
                {"tool_name": b["tool_name"], "description": b.get("description", "")}
                for b in get_runtime_bindings()
            ])
            return
        if path.startswith("/a2a/skills/"):
            skill_id = path[len("/a2a/skills/"):]
            if skill_id.endswith("/invoke"):
                self._json(405, {"error": "MethodNotAllowed", "detail": "use POST for invoke"})
                return
            binding = self.binding_index.get(skill_id)
            if binding is None:
                self._json(404, {"error": "UnknownSkill", "skill_id": skill_id})
                return
            self._json(200, binding)
            return
        self._json(404, {"error": "NotFound", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/a2a/skills/") or not path.endswith("/invoke"):
            self._json(404, {"error": "NotFound", "path": path})
            return
        skill_id = path[len("/a2a/skills/"):-len("/invoke")]
        binding = self.binding_index.get(skill_id)
        if binding is None:
            self._json(404, {"error": "UnknownSkill", "skill_id": skill_id})
            return
        try:
            payload = self._read_body()
        except ValueError as e:
            self._json(400, {"error": "BadRequest", "detail": str(e)})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "BadRequest", "detail": "payload must be JSON object"})
            return
        try:
            require_surface(skill_id, "a2a")
        except KeyError:
            self._json(404, {"error": "UnknownSkill", "skill_id": skill_id})
            return
        try:
            result = get_service().invoke_skill(skill_id, payload)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": type(e).__name__, "detail": str(e), "skill_id": skill_id})
            return
        self._json(200, {"skill_id": skill_id, "result": result})


def serve_http(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    # R-001 prod guard: A2A daemon currently does not perform per-request cookie/CSRF
    # validation; the only access control is the start-up gate below. Refuse to start
    # unless both ZW_BRAIN_DEV_IAM_BYPASS=1 and ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only
    # are set, mirroring REST policy (zw_brain/shared/runtime_config.py).
    if not get_dev_iam_bypass_enabled():
        sys.stderr.write(
            "[a2a] refusing to start: A2A daemon currently has no per-request auth and "
            "must run only with ZW_BRAIN_DEV_IAM_BYPASS=1 + "
            "ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only. "
            "Production should expose A2A via reverse proxy with cookie+CSRF (see module docstring).\n"
        )
        return 2
    _A2AHandler.binding_index = _build_binding_index()
    server = ThreadingHTTPServer((host, port), _A2AHandler)
    server.log_file = os.fdopen(2, "w")  # type: ignore[attr-defined]
    skill_count = len(_A2AHandler.binding_index)
    sys.stderr.write(f"[a2a] zw-brain A2A http://{host}:{port} ({skill_count} skills)\n")
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="zw-brain A2A runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run HTTP daemon for /.well-known/agent.json + /a2a/*")
    serve.add_argument("--host", default=os.environ.get("ZW_BRAIN_A2A_HOST", DEFAULT_HOST))
    serve.add_argument("--port", type=int, default=int(os.environ.get("ZW_BRAIN_A2A_PORT", DEFAULT_PORT)))

    sub.add_parser("agent-card", help="print agent_card.json")

    run = sub.add_parser("invoke", help="one-shot skill invoke")
    run.add_argument("skill_id")
    run.add_argument("--payload", default="{}")

    args = parser.parse_args()

    if args.command == "serve":
        return serve_http(args.host, args.port)

    if args.command == "agent-card":
        print(json.dumps(get_agent_card(), ensure_ascii=False, indent=2))
        return 0

    payload = json.loads(args.payload)
    print(json.dumps(invoke(args.skill_id, payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
