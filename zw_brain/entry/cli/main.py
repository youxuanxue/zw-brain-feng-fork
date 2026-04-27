from __future__ import annotations

import argparse
import json

from zw_brain.shared.runtime import get_service


def main() -> int:
    parser = argparse.ArgumentParser(description="zw-brain CLI")
    parser.add_argument("skill_id", help="registered skill id")
    parser.add_argument("--payload", default="{}", help="JSON payload")
    args = parser.parse_args()
    payload = json.loads(args.payload)
    result = get_service().invoke_skill(args.skill_id, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
