#!/usr/bin/env python3
# .twin/ 6 worker workspace goal+plan schema 提交期守卫。
# trigger fired:
#   - PR #85 — F8 deliverable 与 AC7 文本重合致 supervisor 启动期才发现（schema validate）
#   - PR #117 — 21 处 stale next_action/blocked_reason 在 completed 项遗留（cross-field check）
# 依赖：本机 dev-rules mirror 提供 scripts.twin validate；缺失时跳过 schema validate，但本地
# cross-field check 仍跑（不依赖 dev-rules，纯 yaml 解析）。

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

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


def _check_completed_items_clean(workspaces: list[Path]) -> list[tuple[str, str]]:
    """Cross-field check: completed 项的 next_action 必须为 ''/None，blocked_reason 必须为 None。

    PR #117 触发——supervisor 写 plan.yaml 时把 next_action / blocked_reason append 到
    completed 项却不清理，21 处累积。schema validate 不覆盖此 cross-field 语义。
    """
    failures: list[tuple[str, str]] = []
    for ws in workspaces:
        plan_path = ws / "plan.yaml"
        try:
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            failures.append((ws.name, f"plan.yaml YAML parse failed: {exc}"))
            continue
        for item in plan.get("items") or []:
            if item.get("status") != "completed":
                continue
            item_id = item.get("id", "<unknown>")
            na = item.get("next_action")
            br = item.get("blocked_reason")
            if na not in ("", None):
                failures.append((ws.name, f"{item_id}: status=completed but next_action 非空: {na!r}"))
            if br not in ("", None):
                failures.append((ws.name, f"{item_id}: status=completed but blocked_reason 非空: {br!r}"))
    return failures


def main() -> int:
    if not TWIN_DIR.is_dir():
        print(f"[twin-workspaces] skip: {TWIN_DIR} not present")
        return 0

    workspaces = sorted(p for p in TWIN_DIR.iterdir() if p.is_dir() and (p / "goal.yaml").is_file() and (p / "plan.yaml").is_file())
    if not workspaces:
        print(f"[twin-workspaces] skip: no workspaces under {TWIN_DIR}")
        return 0

    cross_field_failures = _check_completed_items_clean(workspaces)

    dev_rules = _resolve_dev_rules()
    schema_failures: list[tuple[str, str]] = []
    schema_skipped = False
    if dev_rules is None:
        print("[twin-workspaces] partial: scripts.twin schema validate skipped (DEV_RULES env unset and ./dev-rules / ~/Codes/dev-rules missing); cross-field check 仍跑")
        schema_skipped = True
    else:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{dev_rules}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
        for ws in workspaces:
            result = subprocess.run(
                [sys.executable, "-m", "scripts.twin", "validate", str(ws)],
                env=env,
                capture_output=True,
                text=True,
            )
            out = (result.stdout + result.stderr).strip()
            if result.returncode != 0:
                schema_failures.append((ws.name, out))

    if schema_failures or cross_field_failures:
        if schema_failures:
            print(f"[twin-workspaces] FAIL schema: {len(schema_failures)}/{len(workspaces)} workspace(s) failed schema validation")
            for name, msg in schema_failures:
                print(f"  - {name}: {msg}")
        if cross_field_failures:
            print(f"[twin-workspaces] FAIL cross-field: {len(cross_field_failures)} stale field(s) on completed items (PR #117 漂移机械化)")
            for name, msg in cross_field_failures:
                print(f"  - {name}: {msg}")
        return 1

    note = "OK" if not schema_skipped else "OK (schema skipped, cross-field PASS)"
    print(f"[twin-workspaces] {note}: {len(workspaces)} workspace(s) pass scripts.twin validate + cross-field check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
