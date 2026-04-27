from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from zw_brain.shared.runtime import get_service

TOOLS_DIR = Path(__file__).with_name("tools")


def list_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        tools.append(json.loads(path.read_text(encoding="utf-8")))
    return tools


def call_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = get_service().invoke_skill(name, payload)
    return {"tool": name, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="zw-brain MCP runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-tools")
    call = sub.add_parser("call-tool")
    call.add_argument("name")
    call.add_argument("--payload", default="{}")
    args = parser.parse_args()

    if args.command == "list-tools":
        print(json.dumps(list_tools(), ensure_ascii=False, indent=2))
        return 0

    payload = json.loads(args.payload)
    print(json.dumps(call_tool(args.name, payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
