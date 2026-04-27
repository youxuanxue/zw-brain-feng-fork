from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from zw_brain.shared.runtime import get_service

CARD_PATH = Path(__file__).with_name("agent_card.json")


def get_agent_card() -> dict[str, Any]:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def invoke(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = get_service().invoke_skill(skill_id, payload)
    return {"skill_id": skill_id, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="zw-brain A2A runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("agent-card")
    run = sub.add_parser("invoke")
    run.add_argument("skill_id")
    run.add_argument("--payload", default="{}")
    args = parser.parse_args()

    if args.command == "agent-card":
        print(json.dumps(get_agent_card(), ensure_ascii=False, indent=2))
        return 0

    payload = json.loads(args.payload)
    print(json.dumps(invoke(args.skill_id, payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
