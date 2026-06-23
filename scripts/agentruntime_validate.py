#!/usr/bin/env python3
"""Validate zw-brain Agent manifest bundle (AGENT.yaml + capabilities.json)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zw_brain.shared.agent_runtime.manifest_checks import validate_agent_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to AGENT.yaml")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    valid, violations, merged = validate_agent_bundle(args.path)
    agent = merged.get("agent") if isinstance(merged.get("agent"), dict) else {}
    metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}

    if args.json:
        print(
            json.dumps(
                {
                    "valid": valid,
                    "spec_version": merged.get("spec_version"),
                    "agent_id": metadata.get("id"),
                    "trust_level": merged.get("trust_level"),
                    "violations": violations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif valid:
        print(f"[validate] OK: {args.path}")
    else:
        print(f"[validate] FAIL: {args.path}", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)

    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
