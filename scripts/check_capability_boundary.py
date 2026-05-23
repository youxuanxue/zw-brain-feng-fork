#!/usr/bin/env python3
"""check_capability_boundary.py — preflight 段 22

强约束（防止"已发现的禁区前缀回潮"的机械门禁）：
    某 skill_id 落入下方 7 类已发现禁区前缀，且同时 status=live + execution_binding=builtin，
    即视为已清理的越界 manifest 回潮，preflight 必须红灯。

    作用边界（重要，避免误解）：
    - 段 22 只防 builtin live 回潮，不阻止通过 external_capability binding 桥接外部系统
      消费同域能力（例如 external.lineage.graph.build / external.quality.scan.execute
      均为合法形态）。§1.3 禁的是"主 zw-brain 自建"，不是"通过 skill/agent 桥接消费"。
    - 段 22 是事后防回潮，不是 §1.3 完整 10 类的事前防违建——伪装成核心旅程 (j1/j2/b1/infra)
      的新建 builtin 无法靠 prefix 拦下，那属架构约束「能力扩展唯一路径 = Skill 注册」+
      「高频核心走 builtin、长尾默认外部化」+ reviewer 判断范畴。

    禁区前缀来源：docs/approved/zw-brain-architecture.md §1.3 中**已观察到**有 builtin
    越界的 7 类（血缘 / 质量 / 运维监控 / 工单 / 国家通道 / 国家直达 / 标准服务），按
    skill_id prefix 机械分类。§1.3 新增禁区前缀时（例如未来出现 dashboard.* /
    desensitize.* 等 builtin），须同步更新本文件 FORBIDDEN_ZONES。

退出码：
    0 = 全部通过（forbidden-zone 内全部非 live 或非 builtin）
    1 = 至少一条 forbidden-zone live+builtin 越界

使用：
    ./scripts/check_capability_boundary.py
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTERED = REPO / "zw_brain" / "skill_registration" / "registered"

# (zone_label, predicate) — predicate 入参 skill_id 返回 bool
FORBIDDEN_ZONES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("§1.3 血缘", lambda sid: sid.startswith("metadata.lineage.")),
    ("§1.3 质量", lambda sid: sid.startswith("quality.") or sid.startswith("ops.catalog.quality.")),
    ("§1.3 运维监控", lambda sid: sid.startswith("ops.gateway.") or sid.startswith("ops.shift_handover.") or sid == "ops.exchange.diagnose"),
    ("§1.3 工单（外部消息中心）", lambda sid: sid.startswith("ops.ticket.")),
    ("§1.3 国家通道", lambda sid: sid.startswith("adapter.national.")),
    ("§1.3 国家直达", lambda sid: sid.startswith("direct_access.")),
    ("§1.3 标准服务", lambda sid: sid.startswith("standard.")),
)


def classify_zone(skill_id: str) -> str | None:
    for label, pred in FORBIDDEN_ZONES:
        if pred(skill_id):
            return label
    return None


def main() -> int:
    if not REGISTERED.is_dir():
        print(f"[capability-boundary] skip: {REGISTERED} not present")
        return 0

    violations: list[tuple[str, str, str, str]] = []  # (skill_id, zone, status, binding)
    in_zone = 0
    total = 0
    for path in sorted(REGISTERED.glob("*.json")):
        total += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[capability-boundary] FAIL: {path.name}: {exc}")
            return 1
        sid = data.get("skill_id") or path.stem
        zone = classify_zone(sid)
        if zone is None:
            continue
        in_zone += 1
        scope = data.get("product_scope") or {}
        status = scope.get("status", "?")
        binding = data.get("execution_binding", "?")
        if status == "live" and binding == "builtin":
            violations.append((sid, zone, status, binding))

    if violations:
        print(f"[capability-boundary] FAIL: scanned {total} manifests, {in_zone} in forbidden zones, {len(violations)} live+builtin violation(s):")
        for sid, zone, status, binding in violations:
            print(f"  - {sid:50s} {zone:25s} status={status:18s} binding={binding}")
        print()
        print("[capability-boundary] hint: §1.3 不做清单的能力必须 status!=live 或 execution_binding!=builtin；如需放宽，先走 GATE 决策修订 §1.3。")
        return 1

    print(f"[capability-boundary] ok: scanned {total} manifests, {in_zone} in forbidden zones, 0 live+builtin violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
