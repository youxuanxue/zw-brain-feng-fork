#!/usr/bin/env python3
# .twin/ 6 worker workspace goal+plan schema 提交期守卫。
# trigger fired: README §已知未机械化保护点（PR #85 — F8 deliverable 与 AC7 文本重合致 supervisor 启动期才发现）。
# 依赖：本机 dev-rules mirror 提供 scripts.twin validate；缺失时跳过（CI / 新机器环境）。

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TWIN_DIR = REPO_ROOT / ".twin"


def _resolve_dev_rules() -> Path | None:
    for var in ("DEV_RULES", "DEV_RULES_HOME"):
        env = os.environ.get(var)
        if env and (Path(env) / "scripts" / "twin").is_dir():
            return Path(env)
    candidates = [
        REPO_ROOT / "dev-rules",
        Path.home() / "Codes" / "dev-rules",
    ]
    for cand in candidates:
        if (cand / "scripts" / "twin").is_dir():
            return cand
    return None


def main() -> int:
    if not TWIN_DIR.is_dir():
        print(f"[twin-workspaces] skip: {TWIN_DIR} not present")
        return 0

    workspaces = sorted(p for p in TWIN_DIR.iterdir() if p.is_dir() and (p / "goal.yaml").is_file() and (p / "plan.yaml").is_file())
    if not workspaces:
        print(f"[twin-workspaces] skip: no workspaces under {TWIN_DIR}")
        return 0

    dev_rules = _resolve_dev_rules()
    if dev_rules is None:
        print("[twin-workspaces] skip: scripts.twin not resolvable (DEV_RULES env unset and ./dev-rules / ~/Codes/dev-rules missing)")
        return 0

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{dev_rules}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

    failures: list[tuple[str, str]] = []
    for ws in workspaces:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.twin", "validate", str(ws)],
            env=env,
            capture_output=True,
            text=True,
        )
        out = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            failures.append((ws.name, out))

    if failures:
        print(f"[twin-workspaces] FAIL: {len(failures)}/{len(workspaces)} workspace(s) failed schema validation")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        return 1

    print(f"[twin-workspaces] OK: {len(workspaces)} workspace(s) pass scripts.twin validate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
