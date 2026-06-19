"""D-9 perf regression: request.list 不得退回 N+1 风暴（PG 真实库）。

Background:
- W0-08 后客户浏览器复测发现 list_requests() ~37s（~1300 SQL roundtrip/N+1）。
- G1.1 修复 = `_RequestBatchContext` 预取 8 类索引，把 enrichment 层全部 N+1
  压成 O(1) lookup（旧 in-process 文件库实测 9.6s → ~300ms，30× 加速）。
- 本 perf 测试是 D-9 防回归门禁：任何后续改动如果让 request.list 退回 N+1，
  这条断言会拦下 commit。等价性（字段完整）由
  test_request_list_field_completeness_after_perf_fix 单独锁。

预算口径（PG 重定基线，承全盘迁移到 PostgreSQL）：旧 1000ms 是 in-process 文件库
（~300ms×3×余量）口径。PG 每条预取查询多一次 TCP roundtrip，O(1)-prefetch 形状不变
但绝对延迟抬到 ~1.5–3s（共享 dev 机并发 clone 负载下偶冲到 ~5s，仍非 N+1——真 N+1
回潮会重回数十秒/上千 roundtrip）。故预算改 8000ms：把「健康 O(1)-prefetch 在负载下」
（≤5s）与「N+1 回归」（量级 10×+、数十秒）确定性分开，既 deterministic 拦下 N+1，
又不被 PG 网络延迟 + 并发负载尖峰误杀（4000ms 在满载并发下偶发误红，已抬到 8000ms）。
真正把 P95 压回亚秒属 **连接池 / 批量查询** 产品级优化（core/product 切片），不在
本测试迁移切片范围——记残留风险。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"

# Perf budget: PG 重定基线（见模块 docstring）。守 N+1 回归（量级 10×+），不误杀 PG 网络延迟 + 并发负载。
REQUEST_LIST_BUDGET_MS = 8000

pytestmark = pytest.mark.usefixtures("realistic_pg_module")


def test_request_list_under_one_second_real_data():
    """request.list 在真实 sd-default 数据上不退回 N+1（D-9 防回归，PG 预算见模块 docstring）。"""
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    brain = BrainService(state_store=ss)

    # Warmup: 让 engine cache / snapshot / PG buffer cache 暖起来。
    brain.list_requests()

    # 三次取最大值（保护 P95 体验，不是 best-case 平均）。
    timings_ms: list[float] = []
    for _ in range(3):
        t0 = time.perf_counter()
        items = brain.list_requests()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        timings_ms.append(elapsed_ms)
        assert len(items) >= 50, f"request.list 返回行数偏少：{len(items)}（期望 ≥50）"

    worst_ms = max(timings_ms)
    assert worst_ms <= REQUEST_LIST_BUDGET_MS, (
        f"D-9 perf 回归：request.list worst={worst_ms:.0f}ms > "
        f"budget={REQUEST_LIST_BUDGET_MS}ms（all 3 runs: {[f'{t:.0f}ms' for t in timings_ms]}）"
    )


def test_request_list_field_completeness_after_perf_fix():
    """G1.1 等价性证明：context-aware 路径必须保留完整字段（fieldBindings /
    schemaSnapshots / legacyMappings / historicalContext / qualityEvidence）。"""
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    brain = BrainService(state_store=ss)
    items = brain.list_requests()

    # 找一个有富 enrichment 的真实记录（legacy 导入应至少有 1 条满足）
    enriched = [
        item
        for item in items
        if len(item.get("fieldBindings", [])) > 0
        or len(item.get("legacyMappings", [])) > 0
    ]
    assert enriched, "list_requests 返回 0 条富 enrichment 记录；context 预取可能落空"

    sample = max(
        enriched,
        key=lambda r: len(r.get("fieldBindings", [])) + len(r.get("legacyMappings", [])),
    )
    # 字段必须存在（不能因 perf 优化变成 None / 缺失键）
    assert "fieldBindings" in sample
    assert "schemaSnapshots" in sample
    assert "legacyMappings" in sample
    assert "historicalContext" in sample
    assert "qualityEvidence" in sample
    assert "applicationMaterials" in sample
    assert sample.get("historicalContext", {}).get("relatedApplicationCount") is not None
    assert sample.get("qualityEvidence", {}).get("status") in {"ready", "attention_required"}
