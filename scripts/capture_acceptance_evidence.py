#!/usr/bin/env python3
"""capture_acceptance_evidence.py — 效果验收证据采集（D37）

把"验收时真的跑过"固化成一份可机读、带溯源的证据产物,供
`check_acceptance_package.py`（preflight 段 55）校验。**禁止手写 result——
本脚本现场跑 / 现场解析,结果即事实。**

采集三类证据：
  contract  现场跑 `scripts/export_agent_contract.py --check`（exit 0 = pass）
  pytest    现场跑 `pytest -q`（exit 0 = pass；本仓 summary 被抑制,以退出码为准）
  e2e       解析 Playwright list reporter 日志（`N passed` / `N failed`）

产物：`.testing/acceptance/<scope>/evidence.json`（**tracked**,提交进仓,段 55 在
CI 才查得到；`.data/` 是 gitignore 的派生区,不放这里），记 git_sha + captured_at，
SHA 非当前 HEAD 祖先 → 段 55 报陈旧/异线 WARN。

Usage:
    ./scripts/capture_acceptance_evidence.py --scope e5 \
        --deliverable "WebUI / 5 消费面投影" \
        --e2e-log /tmp/e5_e2e.log --e2e-name "customer_acceptance_checklist" \
        --captured-by "薛娇（产品研发负责人）"
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, (out[-1] if out else "")


def check_contract() -> dict:
    py = str(REPO / ".venv" / "bin" / "python")
    py = py if Path(py).exists() else sys.executable
    rc, last = _run([py, "scripts/export_agent_contract.py", "--check"])
    return {"name": "5 消费面投影一致", "kind": "contract",
            "result": "pass" if rc == 0 else "fail", "detail": last}


def check_pytest() -> dict:
    py = str(REPO / ".venv" / "bin" / "python")
    py = py if Path(py).exists() else sys.executable
    rc, last = _run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    return {"name": "后端 / 契约测试套", "kind": "pytest",
            "result": "pass" if rc == 0 else "fail",
            "detail": f"exit {rc}（本仓 summary 抑制,以退出码为准）"}


def check_e2e(log_path: str, name: str) -> dict:
    txt = Path(log_path).read_text(encoding="utf-8", errors="ignore") if Path(log_path).exists() else ""
    passed = int(m.group(1)) if (m := re.search(r"(\d+)\s+passed", txt)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+)\s+failed", txt)) else 0
    skipped = int(m.group(1)) if (m := re.search(r"(\d+)\s+skipped", txt)) else 0
    result = "pass" if (txt and failed == 0 and passed > 0) else "fail"
    return {"name": f"WebUI 活跑验收（{name}）", "kind": "e2e", "result": result,
            "detail": f"{passed} passed / {failed} failed / {skipped} skipped"}


def main() -> int:
    ap = argparse.ArgumentParser(description="效果验收证据采集（D37）")
    ap.add_argument("--scope", required=True, help="验收范围,如 e5")
    ap.add_argument("--deliverable", default="", help="一句话交付物")
    ap.add_argument("--e2e-log", help="Playwright list reporter 日志路径")
    ap.add_argument("--e2e-name", default="e2e", help="e2e 套名")
    ap.add_argument("--captured-by", default="", help="采集人")
    args = ap.parse_args()

    checks = [check_contract(), check_pytest()]
    if args.e2e_log:
        checks.append(check_e2e(args.e2e_log, args.e2e_name))

    artifact = {
        "scope": args.scope,
        "deliverable": args.deliverable,
        "git_sha": _git_sha(),
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "captured_by": args.captured_by,
        "checks": checks,
    }
    out_dir = REPO / ".testing" / "acceptance" / args.scope
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "evidence.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fails = [c for c in checks if c["result"] != "pass"]
    print(f"[capture-acceptance] wrote {out.relative_to(REPO)} — {len(checks)} check(s), {len(fails)} fail")
    for c in checks:
        print(f"  [{c['result']}] {c['name']}: {c['detail']}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
