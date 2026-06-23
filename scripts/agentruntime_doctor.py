#!/usr/bin/env python3
"""Diagnose zw-brain Agent readiness (AGENT.yaml + capabilities.json)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zw_brain.shared.agent_runtime.manifest_checks import diagnose_agent_bundle  # noqa: E402

SEVERITY_ORDER = {"OK": 0, "HINT": 1, "WARN": 2, "FAIL": 3}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to AGENT.yaml or agent directory")
    parser.add_argument("--target", choices=("dev", "production"), default="dev")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    agent_yaml = args.path
    if agent_yaml.is_dir():
        agent_yaml = agent_yaml / "AGENT.yaml"
    if not agent_yaml.is_file():
        print(f"[doctor] missing AGENT.yaml: {agent_yaml}", file=sys.stderr)
        return 1

    diagnoses = diagnose_agent_bundle(agent_yaml, production=args.target == "production")
    diagnoses.sort(key=lambda item: SEVERITY_ORDER.get(item[0], 9), reverse=True)
    has_fail = any(sev == "FAIL" for sev, _, _ in diagnoses)

    if args.json:
        print(
            json.dumps(
                [{"severity": s, "area": a, "message": m} for s, a, m in diagnoses],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"[doctor] {agent_yaml} — {len(diagnoses)} checks")
        for sev, area, msg in diagnoses:
            print(f"  [{sev}]\t{area}\t{msg}")

    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
