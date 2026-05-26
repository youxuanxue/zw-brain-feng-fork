#!/usr/bin/env python3
"""check_live_builtin_budget.py — preflight 段 33

强约束（防止"按域均匀长 capability"反架构约束 R7 的机械门禁）：
    单个 skill_id prefix 下 live+builtin manifest 数 > N（当前 N=25）即视为
    "按域均匀长而非按频度收敛"——违背基线架构约束 R7「外部长尾注册优先，主仓库
    只承接高频核心与底座」（确定性自动化运营和运维下，长尾能力默认转向外部能力包路径）。
    preflight 必须红灯，开发者必须三选一：
      (a) 拆 prefix（拒绝"按域均匀长"，重新归属到更细分的命名空间）；
      (b) 把其中部分 mark deferred / external（status != live 或 binding != builtin）；
      (c) 在 scripts/.live_builtin_budget_exemptions.json 显式登记豁免 +
          配 architecture-review issue 链接走 R-编号决策。

    上下文：
    - 截至 2026-05-26 main HEAD，单 prefix max = catalog 23（≤ 25，PASS）。
    - 该门禁与段 22 capability-boundary 互补：段 22 防 forbidden-zone 回潮，
      段 33 防"未越界但聚合入口配 N 个 capability 长尾累积"反架构约束 R7。

    与基线关联：
    - 架构约束 R7「外部长尾注册优先，主仓库只承接高频核心与底座」
    - 架构约束 R4「控制面必须存在，但以最小可用为先」（capability 越多
      Registry / Policy / Audit 维护面越宽）
    - §6.6 5 消费面投影派生自单一 Registry — 单 prefix 越界即代表 UI 聚合
      入口被"按域均匀长"撑出去，与精简 WebUI ≤10 核心场景页 (D8) 张力。
    - 配合本 PR commit "feat(preflight): 段 33 live-builtin-budget"

退出码：
    0 = 全部通过（每个 prefix 计数 ≤ N，或在豁免清单内）
    1 = 至少一个 prefix 越界 N 且未豁免

使用：
    ./scripts/check_live_builtin_budget.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_REGISTERED = REPO / "zw_brain" / "skill_registration" / "registered"
DEFAULT_EXEMPTIONS = REPO / "scripts" / ".live_builtin_budget_exemptions.json"

# Budget threshold — single prefix live+builtin count limit
BUDGET_N = 25


def load_exemptions(path: Path) -> dict[str, int]:
    """Return {prefix: max_allowed_count}. Keys starting with '_' are ignored (comments)."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[live-builtin-budget] FAIL: cannot parse {path}: {exc}")
        sys.exit(1)
    return {k: int(v) for k, v in data.items() if not k.startswith("_")}


def count_live_builtin_by_prefix(registered_dir: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for f in sorted(registered_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[live-builtin-budget] FAIL: cannot parse {f.name}: {exc}")
            sys.exit(1)
        scope = data.get("product_scope") or {}
        if scope.get("status") != "live":
            continue
        if data.get("execution_binding") != "builtin":
            continue
        sid = data.get("skill_id") or f.stem
        prefix = sid.split(".")[0]
        counts[prefix] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registered-dir",
        type=Path,
        default=DEFAULT_REGISTERED,
        help="目录路径（默认 zw_brain/skill_registration/registered/）",
    )
    parser.add_argument(
        "--exemptions",
        type=Path,
        default=DEFAULT_EXEMPTIONS,
        help="豁免清单 JSON 路径（默认 scripts/.live_builtin_budget_exemptions.json）",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=BUDGET_N,
        help=f"单 prefix live+builtin 上限（默认 N={BUDGET_N}）",
    )
    args = parser.parse_args(argv)

    if not args.registered_dir.is_dir():
        print(f"[live-builtin-budget] skip: {args.registered_dir} not present")
        return 0

    exemptions = load_exemptions(args.exemptions)
    counts = count_live_builtin_by_prefix(args.registered_dir)
    total = sum(counts.values())

    violations: list[tuple[str, int, int]] = []  # (prefix, count, effective_limit)
    for prefix, count in counts.items():
        limit = exemptions.get(prefix, args.budget)
        if count > limit:
            violations.append((prefix, count, limit))

    if violations:
        print(
            f"[live-builtin-budget] FAIL: scanned {total} live+builtin manifest(s), "
            f"{len(violations)} prefix over budget (N={args.budget})"
        )
        for prefix, count, limit in violations:
            tag = "exempt-limit" if prefix in exemptions else "budget"
            print(f"  - {prefix:20s} count={count:3d}  {tag}={limit}")
        print()
        print("[live-builtin-budget] hint: 单 prefix > N 触发架构约束 R7 review，三选一：")
        print("  (a) 拆 prefix（更细分命名空间，拒绝按域均匀长）")
        print("  (b) 部分 capability 改 status != live 或 execution_binding != builtin")
        print("  (c) scripts/.live_builtin_budget_exemptions.json 显式登记豁免 +")
        print("      配 architecture-review issue 链接（R-编号决策）")
        return 1

    headroom = ", ".join(
        f"{p}={c}"
        for p, c in counts.most_common(5)
    )
    print(
        f"[live-builtin-budget] ok: scanned {total} live+builtin manifest(s), "
        f"max prefix ≤ {args.budget} (top5: {headroom})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
