"""zw-brain-cli — capability headless 调用入口。

设计：
- 单一 console_script entry point（pyproject.toml `zw-brain-cli`），不引 rich/click 等花哨依赖。
- 默认走 in-process invoke (`zw_brain.command.runtime.get_service`)；--endpoint 切到 HTTP。
- --list / --describe 从 F4 派生的 commands.generated.json 切，不重复枚举 <!-- stat:zwbrain.manifest-total -->200<!-- /stat --> manifest。
- 失败语义清晰：unknown skill = 2 / bad payload = 3 / invoke failure = 4。

使用示例：
    zw-brain-cli --list                                   # 列出全部 capability（计数见输出行尾）
    zw-brain-cli --list catalog                           # 前缀过滤
    zw-brain-cli --describe workbench.view                # description + roles + args
    zw-brain-cli workbench.view --role ROLE_ORGAN_OPERATER
    zw-brain-cli request.create --payload '{"resource_id":"res-jbxx-ledger"}'
    zw-brain-cli workbench.view --endpoint http://127.0.0.1:8800
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from zw_brain.shared.logkit import (
    bind_request_context,
    get_request_id,
    reset_request_context,
    setup_logging,
)

CLI_ROOT = Path(__file__).resolve().parent
COMMANDS_PATH = CLI_ROOT / "commands.generated.json"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_UNKNOWN_SKILL = 2
EXIT_BAD_PAYLOAD = 3
EXIT_INVOKE_FAILED = 4

DEFAULT_ROLE = "ROLE_ORGAN_OPERATER"


def _load_commands() -> dict[str, Any]:
    if not COMMANDS_PATH.exists():
        return {"commands": []}
    return json.loads(COMMANDS_PATH.read_text(encoding="utf-8"))


def _command_by_id(data: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    for cmd in data.get("commands", []):
        if cmd.get("skill_id") == skill_id:
            return cmd
    return None


def _resolve_default_role() -> str:
    # dev bypass 默认用 ORGAN_OPERATER（与 workbench.view fixture 主角色一致）。
    # 生产应通过 --role 显式指定，或带有效 cookie/JWT 调 --endpoint。
    return os.environ.get("ZW_BRAIN_CLI_ROLE", DEFAULT_ROLE)


def cmd_list(prefix: str | None, data: dict[str, Any]) -> int:
    commands = data.get("commands", [])
    if prefix:
        commands = [c for c in commands if str(c.get("skill_id", "")).startswith(prefix)]
    if not commands:
        print(f"[cli] no commands matching prefix={prefix!r}", file=sys.stderr)
        return EXIT_OK
    for cmd in commands:
        mode = cmd.get("mode", "read")
        confirm = " (confirm)" if cmd.get("human_confirmation_required") else ""
        title = cmd.get("title", "") or cmd.get("description", "")[:40]
        print(f"{cmd['skill_id']:50}  [{mode}]{confirm}  {title}")
    print(f"\n[cli] {len(commands)} commands (source: commands.generated.json)", file=sys.stderr)
    return EXIT_OK


def cmd_describe(skill_id: str, data: dict[str, Any]) -> int:
    cmd = _command_by_id(data, skill_id)
    if cmd is None:
        print(f"[cli] unknown skill_id: {skill_id}", file=sys.stderr)
        print("  use `zw-brain-cli --list` to discover available skills", file=sys.stderr)
        return EXIT_UNKNOWN_SKILL
    print(f"skill_id:    {cmd['skill_id']}")
    print(f"title:       {cmd.get('title','')}")
    print(f"description: {cmd.get('description','')}")
    print(f"mode:        {cmd.get('mode','read')}")
    print(f"audit:       {cmd.get('audit_required', False)}")
    print(f"confirm:     {cmd.get('human_confirmation_required', False)}")
    print("args:")
    args = cmd.get("args") or []
    if not args:
        print("  (no input arguments)")
    for arg in args:
        req = "*" if arg.get("required") else " "
        print(f"  {req} {arg['name']:30}  {arg.get('type','string')}")
    print("\ninvoke example:")
    sample = {a["name"]: f"<{a.get('type','string')}>" for a in args if a.get("required")}
    sample_json = json.dumps(sample, ensure_ascii=False) if sample else "{}"
    print(f"  zw-brain-cli {skill_id} --payload '{sample_json}'")
    return EXIT_OK


def _invoke_inprocess(skill_id: str, payload: dict[str, Any]) -> tuple[int, Any]:
    """In-process invoke (no HTTP); needs project deps + dev IAM bypass for auth."""
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

    # M5 prod guard (symmetric with A2A serve_http / MCP serve_stdio): the in-process
    # invoke path below binds the dev-iam-bypass synthetic full-role identity. Refuse to
    # run it under a prod deploy mode instead of failing open — calling the gate raises
    # DevBypassInProductionError only when ZW_BRAIN_DEPLOY_MODE is prod/production AND the
    # bypass env is present; non-prod returns normally regardless. (--list / --describe /
    # --endpoint HTTP paths never reach here, so they stay usable.)
    try:
        get_dev_iam_bypass_enabled()
    except DevBypassInProductionError as exc:
        return EXIT_INVOKE_FAILED, {
            "error": "DevBypassInProductionError",
            "detail": str(exc),
            "skill_id": skill_id,
        }
    try:
        require_surface(skill_id, "cli")
    except KeyError:
        return EXIT_UNKNOWN_SKILL, {"error": "UnknownSkill", "detail": skill_id, "skill_id": skill_id}
    except Exception as e:  # noqa: BLE001
        return EXIT_INVOKE_FAILED, {"error": type(e).__name__, "detail": str(e), "skill_id": skill_id}
    # Bind the dev-bypass synthetic identity so the shared C1/N1 boundary resolver enforces
    # role-holding for CLI in-process calls (a forged --role is rejected for writes / degraded
    # for reads) exactly as for REST/MCP/A2A. CLI runs only under dev-IAM-bypass.
    token = set_auth_context(dev_iam_bypass_auth_context())
    try:
        result = get_service().invoke_skill(skill_id, payload)
        return EXIT_OK, result
    except KeyError as e:
        return EXIT_INVOKE_FAILED, {"error": "KeyError", "detail": str(e), "skill_id": skill_id}
    except NotImplementedError as e:
        return EXIT_INVOKE_FAILED, {"error": "NotImplementedError", "detail": str(e), "skill_id": skill_id}
    except Exception as e:  # noqa: BLE001 — top-level CLI boundary, surface as JSON
        return EXIT_INVOKE_FAILED, {
            "error": type(e).__name__,
            "detail": str(e),
            "skill_id": skill_id,
        }
    finally:
        reset_auth_context(token)


def _invoke_http(endpoint: str, skill_id: str, payload: dict[str, Any]) -> tuple[int, Any]:
    """HTTP invoke against REST gateway (/api/skills/<id> POST)."""
    url = f"{endpoint.rstrip('/')}/api/skills/{skill_id}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if get_request_id():
        # 贯穿到远端 REST 日志：同一 id 可在 rest.log 里串出服务端链路
        headers["X-Request-Id"] = get_request_id()
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return EXIT_OK, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            body = {"error": "HTTPError", "status": e.code}
        return EXIT_INVOKE_FAILED, body
    except urllib.error.URLError as e:
        return EXIT_INVOKE_FAILED, {"error": "URLError", "detail": str(e.reason)}


def cmd_invoke(skill_id: str, payload_str: str, role: str, endpoint: str | None, data: dict[str, Any]) -> int:
    cmd = _command_by_id(data, skill_id)
    if cmd is None:
        print(f"[cli] unknown skill_id: {skill_id}", file=sys.stderr)
        print("  use `zw-brain-cli --list` to discover available skills", file=sys.stderr)
        return EXIT_UNKNOWN_SKILL
    try:
        payload = json.loads(payload_str) if payload_str else {}
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[cli] bad --payload JSON: {e}", file=sys.stderr)
        print(f"  received: {payload_str!r}", file=sys.stderr)
        return EXIT_BAD_PAYLOAD

    payload.setdefault("role", role)
    # Sticky confirmation — policy.py:386 enforces `human_confirmation_required` runtime gate.
    # Running `zw-brain-cli <write_skill>` IS the operator's explicit confirmation; without
    # this default, ~130 write skills would be silently rejected. To opt out (e.g. dry-run
    # before a destructive op), pass `--payload '{"confirmed":false}'` explicitly.
    payload.setdefault("confirmed", True)

    tokens = bind_request_context(entry="cli")
    try:
        if endpoint:
            code, result = _invoke_http(endpoint, skill_id, payload)
        else:
            code, result = _invoke_inprocess(skill_id, payload)
    finally:
        reset_request_context(tokens)

    if code == EXIT_OK:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 失败时输出结构化错误到 stderr 不污染 stdout（便于脚本 piping）
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zw-brain-cli",
        description="zw-brain headless CLI — capability via single entry. See --list / --describe.",
    )
    p.add_argument("skill_id", nargs="?", help="registered skill id (e.g. workbench.view)")
    p.add_argument("--payload", default="", help="JSON payload (default: {})")
    p.add_argument("--role", default=None, help=f"role code (default: {DEFAULT_ROLE} or $ZW_BRAIN_CLI_ROLE)")
    p.add_argument(
        "--endpoint",
        default=None,
        help="HTTP base URL (e.g. http://127.0.0.1:8800); omit to use in-process invoke",
    )
    p.add_argument("--list", nargs="?", const="", metavar="PREFIX", help="list available skills (optional prefix filter)")
    p.add_argument("--describe", metavar="SKILL_ID", help="show skill description + args schema")
    return p


def main() -> int:
    setup_logging("cli")
    parser = build_parser()
    args = parser.parse_args()
    data = _load_commands()
    if args.list is not None:
        return cmd_list(args.list or None, data)
    if args.describe:
        return cmd_describe(args.describe, data)
    if not args.skill_id:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    role = args.role or _resolve_default_role()
    return cmd_invoke(args.skill_id, args.payload, role, args.endpoint, data)


if __name__ == "__main__":
    raise SystemExit(main())
