#!/usr/bin/env python3
"""Wave 4 legacy 退役准备度看板.

docs/customer-readiness/wave4-cutoff-criteria.md 5 类判据机械化：
  A. J1 替代验证（90 天 SLI）   — 客户上线后由监控接入
  B. J2 替代验证（90 天 SLI）   — 同
  C. B1 合规底线覆盖             — 同
  D. 长尾外部能力包覆盖           — 业务方签字 + 客户回访
  E. Legacy 写入口已切断          — preflight 段 + 客户机房 API gateway 日志

本脚本以 yaml + signoff doc 状态为输入，输出退役准备度百分比。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
LEGACY_SMOKE_YAML = REPO / "tests" / "fixtures" / "legacy_smoke.yaml"
SIGNOFF_DOC = REPO / "docs" / "legacy-not-reproduce-signoff.md"
CUTOFF_DOC = REPO / "docs" / "customer-readiness" / "wave4-cutoff-criteria.md"


def _load_smoke_entries() -> list[dict]:
    if not LEGACY_SMOKE_YAML.is_file():
        return []
    return yaml.safe_load(LEGACY_SMOKE_YAML.read_text(encoding="utf-8")) or []


def _signoff_doc_status() -> str:
    if not SIGNOFF_DOC.is_file():
        return "missing"
    text = SIGNOFF_DOC.read_text(encoding="utf-8")
    m = re.search(r"^status:\s*(\S+)", text, flags=re.MULTILINE)
    return m.group(1) if m else "unknown"


def _criterion_a_j1_sli() -> tuple[int, int, str]:
    """判据 A: J1 替代验证 90 天 SLI（客户上线后由监控 cron 喂入）"""
    # 当前阶段：无客户上线，0%
    return 0, 1, "等首客户上线 90 天 SLI 监控"


def _criterion_b_j2_sli() -> tuple[int, int, str]:
    return 0, 1, "等首客户上线 90 天 SLI 监控"


def _criterion_c_b1_compliance() -> tuple[int, int, str]:
    return 0, 1, "等 Wave 2 B1.1/B1.2 三引擎 land + 客户验收"


def _criterion_d_long_tail(entries: list[dict], signoff_status: str) -> tuple[int, int, str]:
    """判据 D: 长尾覆盖 = not_reproduce ❌ + deferred ⏸ + external ⚠ 全部有处置（数量从 yaml 实测）"""
    not_repro = [e for e in entries if e.get("disposition") == "not_reproduce"]
    deferred = [e for e in entries if e.get("disposition") == "deferred"]
    external = [e for e in entries if e.get("disposition") == "external"]
    total = len(not_repro) + len(deferred) + len(external)
    if total == 0:
        return 0, 1, "legacy_smoke.yaml 未生成或无非 mapped 条目"

    disposed = 0
    # not_reproduce 处置 = 业务方签字
    if signoff_status == "approved":
        disposed += len(not_repro)
    # deferred 处置 = 仅当客户上线后回访接受才算
    # external 处置 = 集团服务联通后算
    # 当前阶段两者都尚未处置

    rationale = (
        f"not_reproduce {len(not_repro)} 条："
        + ("已业务方签字" if signoff_status == "approved" else "待业务方下次 review 签字")
        + f"；deferred {len(deferred)} + external {len(external)} 条等客户上线后处置"
    )
    return disposed, total, rationale


def _criterion_e_write_entry_cut() -> tuple[int, int, str]:
    """判据 E: legacy 写入口流量 = 0（客户机房 API gateway 监控）"""
    feature_path = REPO / ".testing" / "waves" / "wave-4-legacy-retirement" / "features" / "legacy-write-entry-deprecation.feature"
    if not feature_path.is_file():
        return 0, 1, "legacy-write-entry-deprecation.feature 缺失"
    # 当前阶段：尚未上线
    return 0, 1, "等客户机房部署 + API gateway 日志接入"


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 4 legacy 退役准备度看板")
    parser.add_argument("--check", action="store_true", help="CI 模式（始终 exit 0，仅显示当前进度）")
    args = parser.parse_args()

    entries = _load_smoke_entries()
    signoff_status = _signoff_doc_status()

    print("═" * 87)
    print("Legacy Retirement Readiness — Wave 4 退役准备度")
    print("  driven_by: docs/customer-readiness/wave4-cutoff-criteria.md")
    print("  飞轮 §九 反模式 #8 — 90 天 SLI 走监控不走 GWT")
    print("═" * 87)
    print()

    criteria = [
        ("A. J1 替代验证（90 天 SLI）", _criterion_a_j1_sli()),
        ("B. J2 替代验证（90 天 SLI）", _criterion_b_j2_sli()),
        ("C. B1 合规底线覆盖", _criterion_c_b1_compliance()),
        ("D. 长尾外部能力包覆盖", _criterion_d_long_tail(entries, signoff_status)),
        ("E. Legacy 写入口已切断", _criterion_e_write_entry_cut()),
    ]

    total_done = 0
    total_target = 0
    for name, (done, target, note) in criteria:
        pct = (done * 100 // target) if target > 0 else 0
        bars = pct // 10
        bar = "█" * bars + "░" * (10 - bars)
        marker = "✓" if done >= target and target > 0 else "⏳"
        print(f"  {name}")
        print(f"     [{bar}] {done}/{target}  {marker}  {note}")
        print()
        total_done += done
        total_target += target

    overall_pct = (total_done * 100 // total_target) if total_target > 0 else 0
    print("─" * 87)
    print(f"  Retirement Gate Overall: {total_done} / {total_target}  ({overall_pct}%)")
    if overall_pct >= 100:
        print("  ✓ legacy 可关闭写入口（请走最终审批）")
    else:
        print("  ⏳ legacy 退役尚未达成；当前阶段：势能积累期（首客户尚未上线）")
    print()
    print(f"  xlsx 用例 disposition 分布（{len(entries)} 行）:")
    if entries:
        counts: dict[str, int] = {}
        for e in entries:
            counts[e.get("disposition", "unknown")] = counts.get(e.get("disposition", "unknown"), 0) + 1
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    - {k}: {v}")
    else:
        print("    - legacy_smoke.yaml 未生成（pytest 跑 scripts/extract_legacy_smoke_xlsx.py）")
    print("═" * 87)

    return 0


if __name__ == "__main__":
    sys.exit(main())
