#!/usr/bin/env python3
"""check_agentruntime_bundles.py — preflight 段（D33.b retrofit）

D30 (2026-05-24) 决策：AgentRuntime runtime 触发式落地，validate / doctor 工具链
在 T1（首个真实外部 Agent 接入）触发当日 land。当前 agents/ 下已有内置 Agent
样例（如 zw_search_helper），D33.b (2026-05-28) 把 validate 接入 preflight，作
为持续 CI 守卫：保证已存在的 AGENT.yaml + capabilities.json bundle 一直处于
有效状态（schema_version 合法 / trust_level 合法 / model.provider 走集团推理
平台 / permissions.scopes 不触禁区 / capability_tools 引用的 slug 存在等）。

判定规则：
    - 扫 agents/ 下所有 */AGENT.yaml
    - 对每个调 zw_brain.shared.agent_runtime.manifest_checks.validate_agent_bundle
    - 任一 bundle 违规 → 红灯

退出码：
    0 = 通过（所有 bundle 有效或 agents/ 不存在）
    1 = 至少一个 bundle 违规

使用：
    PYTHON_BIN=$REPO_ROOT/.venv/bin/python ./scripts/check_agentruntime_bundles.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AGENTS_DIR = REPO / "agents"


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print("[agentruntime-bundles] skip: agents/ not present")
        return 0

    # agents/ 存在意味着已有外部 / 内置 Agent 入仓，validate_agent_bundle 必须可用；
    # import 失败属于 agent_runtime 模块 broken（schema 不再受守卫），必须 FAIL 而非 skip。
    try:
        from zw_brain.shared.agent_runtime.manifest_checks import validate_agent_bundle
    except ImportError as exc:
        print(f"[agentruntime-bundles] FAIL: agents/ present but validate_agent_bundle import failed ({exc})")
        return 1

    bundles = sorted(AGENTS_DIR.glob("*/AGENT.yaml"))
    if not bundles:
        print("[agentruntime-bundles] ok: agents/ exists but no AGENT.yaml found")
        return 0

    failed: list[tuple[Path, list[str]]] = []
    for bundle in bundles:
        valid, violations, _merged = validate_agent_bundle(bundle)
        if not valid:
            failed.append((bundle, violations))

    if failed:
        print(f"[agentruntime-bundles] FAIL: {len(failed)}/{len(bundles)} AGENT.yaml bundle(s) invalid:")
        for bundle, violations in failed:
            rel = bundle.relative_to(REPO)
            print(f"  - {rel}")
            for item in violations:
                print(f"      {item}")
        return 1

    print(f"[agentruntime-bundles] ok: {len(bundles)} bundle(s) valid (D33.b — D30 4 字段守卫)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
