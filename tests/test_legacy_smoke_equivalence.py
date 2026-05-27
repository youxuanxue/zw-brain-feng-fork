"""旧 xlsx ✅ mapped 用例等价回归骨架（飞轮 §三.2 真值源 → tests 链路）.

zw-brain 飞轮势能源之一 → 验证证据层的机械连接：
  old/共享平台V5.0.2-冒烟.xlsx
       ↓ scripts/extract_legacy_smoke_xlsx.py
  tests/fixtures/legacy_smoke.yaml (131 entries)
       ↓ pytest parametrize（本文件）
  每条 ✅ mapped 用例 = 1 个 test case，跑在 sd-default 真实 dump 上
       ↓
  失败信号: "旧 xlsx 行 N: <用例名> 在新平台上失败"

本文件落地"骨架"阶段：
  - parametrize 加载所有 ✅ mapped 条目
  - test_smoke_equivalence_skeleton — 当前 xfail，证明 fixture 可消费 + 元数据完整
  - 各 wave 实施 PR 接力把 xfail 转为真实业务调用 + 断言

不在本文件范围（避免过度抽象）：
  - 真实业务调用链路 — 由 e1/e2/e4 各 worker 在自己的 wave PR 实施时填充
  - mapped 用例逐条覆盖 — 增量；e6 AC6 / Wave 4 退役判据闭合时统一兑现

Feature-ref:
  .testing/cross-cutting/legacy-128-mapping.md
  docs/approved/zw-brain-flywheel.md §三.2 真值源 5
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
FIXTURE_YAML = REPO / "tests" / "fixtures" / "legacy_smoke.yaml"


def _load_legacy_smoke_fixture() -> list[dict[str, Any]]:
    """加载 legacy_smoke.yaml；缺失 → 跳过整套（CI / fresh checkout 容错）"""
    if not FIXTURE_YAML.is_file():
        return []
    return yaml.safe_load(FIXTURE_YAML.read_text(encoding="utf-8")) or []


_ALL_ENTRIES = _load_legacy_smoke_fixture()
_MAPPED_ENTRIES = [e for e in _ALL_ENTRIES if e.get("disposition") == "mapped"]


@pytest.fixture(scope="module")
def legacy_smoke_entries() -> list[dict[str, Any]]:
    return _ALL_ENTRIES


def test_fixture_present_and_well_formed(legacy_smoke_entries: list[dict[str, Any]]) -> None:
    """飞轮势能源 → tests/fixtures 的连接：yaml 存在且每条有必备字段"""
    if not legacy_smoke_entries:
        pytest.skip("legacy_smoke.yaml 缺失（CI / fresh checkout）")

    required_fields = {"xlsx_row", "name", "system", "priority", "disposition"}
    for entry in legacy_smoke_entries:
        missing = required_fields - set(entry.keys())
        assert not missing, f"行 {entry.get('xlsx_row')} 缺字段: {missing}"
        assert entry["disposition"] in {
            "mapped",
            "not_reproduce",
            "deferred",
            "external",
            "unmapped",
        }, f"行 {entry['xlsx_row']}: 未知 disposition {entry['disposition']!r}"


def test_mapped_entries_have_feature_ref(legacy_smoke_entries: list[dict[str, Any]]) -> None:
    """mapped 条目必须有 feature_ref（指向 .testing/waves/.../*.feature）"""
    if not legacy_smoke_entries:
        pytest.skip("legacy_smoke.yaml 缺失")

    mapped_without_ref = [
        e for e in legacy_smoke_entries
        if e.get("disposition") == "mapped" and not e.get("feature_ref")
    ]
    assert not mapped_without_ref, (
        f"{len(mapped_without_ref)} 条 mapped 用例缺 feature_ref："
        + ", ".join(f"行{e['xlsx_row']} '{e['name']}'" for e in mapped_without_ref[:5])
    )


def test_not_reproduce_entries_have_rationale(legacy_smoke_entries: list[dict[str, Any]]) -> None:
    """not_reproduce 必须有 rationale（业务方签字依据 — docs/legacy-not-reproduce-signoff.md）.

    deferred / external 不强制：disposition 本身已语义化，mapping doc 顶部统一说明
    （飞轮 §三.2 真值源 + 50 条不复刻清单签字载体）。
    """
    if not legacy_smoke_entries:
        pytest.skip("legacy_smoke.yaml 缺失")

    missing = [
        e for e in legacy_smoke_entries
        if e.get("disposition") == "not_reproduce" and not e.get("rationale")
    ]
    assert not missing, (
        f"{len(missing)} 条 not_reproduce 用例缺 rationale（业务方签字将无依据）："
        + ", ".join(f"行{e['xlsx_row']} '{e['name']}'" for e in missing[:5])
    )


@pytest.mark.xfail(
    reason="飞轮 §三.2 等价回归骨架 — 各 wave 实施 PR 接力把 xfail 转为真实业务调用",
    strict=False,
)
@pytest.mark.parametrize(
    "entry",
    _MAPPED_ENTRIES,
    ids=[f"row{e['xlsx_row']}-{e['name']}" for e in _MAPPED_ENTRIES] if _MAPPED_ENTRIES else ["empty"],
)
def test_legacy_equivalent_on_sd_default(entry: dict[str, Any]) -> None:
    """旧 xlsx 行 N: <用例名> 在 sd-default 真实 dump 上等价跑通.

    各 wave 实施 PR 把这个 xfail stub 替换为真实链路：
      1. 按 entry.steps 调用新平台 capability
      2. 断言 entry.expected
      3. 验证 audit_event / 状态机迁移等可观测断言

    当前 xfail = 飞轮势能源 → tests 骨架已 land，等业务调用实施。
    """
    if not entry:
        pytest.skip("空 entry")
    pytest.fail(f"旧 xlsx 行 {entry['xlsx_row']}: {entry['name']} — 等价回归未实施")


def test_disposition_distribution_sanity(legacy_smoke_entries: list[dict[str, Any]]) -> None:
    """飞轮势能源完整性：disposition 分布应覆盖 xlsx 全部 131 行 + 飞轮设计 §三.2 类型一致"""
    if not legacy_smoke_entries:
        pytest.skip("legacy_smoke.yaml 缺失")

    counts: dict[str, int] = {}
    for e in legacy_smoke_entries:
        counts[e["disposition"]] = counts.get(e["disposition"], 0) + 1

    total = sum(counts.values())
    assert total >= 100, f"xlsx 行数过少 ({total} < 100)；可能 xlsx 截断"
    assert counts.get("mapped", 0) >= 50, (
        f"mapped 仅 {counts.get('mapped', 0)} 条；飞轮设计下限 ≥50 条 ✅"
    )
