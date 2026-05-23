"""D-9 perf regression: request.list must run ≤1s end-to-end on sd-default.

Background:
- W0-08 后客户浏览器复测发现 list_requests() ~37s（~1300 SQL roundtrip/N+1）。
- G1.1 修复 = `_RequestBatchContext` 预取 8 类索引，把 enrichment 层全部 N+1
  压成 O(1) lookup，实测 9.6s → ~300ms（30× 加速）。
- 本 perf 测试是 D-9 的 PR-G1 防回归门禁：任何后续改动如果让 request.list
  退回 ≥1s，这条断言会拦下 commit。

Data dependency: 复用 SHADOW_DB（test_W0-05_shadow.db），与 wave0 其他真数据测试同源。
不依赖 capability_call（其它测试可能 reset_and_upgrade 清空），只依赖 application_record /
delivery_task / legacy_object_mapping / quality_evidence_projection / resource_assets /
schema_mappings / schema_snapshots / catalog_items —— 均为 seed 数据，运行时不被改动。
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_perf_request_list_shadow.db"
TENANT = "sd-default"

# Perf budget: 1s P95 客户体感上限（G1.1 实测 ~300ms，留 3× 余量）。
REQUEST_LIST_BUDGET_MS = 1000


def _real_data_ready() -> bool:
    if not SEED_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM application_record WHERE tenant_id=?", (TENANT,)
            ).fetchone()
            return bool(row and row[0] >= 200)
    except sqlite3.OperationalError:
        return False


if not _real_data_ready():
    pytest.skip(
        "W0-02 legacy 真灌库 数据缺位（CI runner 不带 .data/zw_brain.db）；"
        "本地真数据验收承接 D-9 perf budget，证据见 .data/customer-acceptance/wave0/",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def _shadow_db():
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    shutil.copy(SEED_DB, SHADOW_DB)
    prev_path = os.environ.get("ZW_BRAIN_DB_PATH")
    prev_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    yield
    if prev_path is None:
        os.environ.pop("ZW_BRAIN_DB_PATH", None)
    else:
        os.environ["ZW_BRAIN_DB_PATH"] = prev_path
    if prev_url is not None:
        os.environ["ZW_BRAIN_DATABASE_URL"] = prev_url
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()


def test_request_list_under_one_second_real_data():
    """request.list 在真实 sd-default 数据上 ≤1s（D-9 防回归）。"""
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    brain = BrainService(state_store=ss)

    # Warmup: 让 engine cache / snapshot / sqlite page cache 暖起来。
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
