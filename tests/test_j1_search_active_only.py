# Wave: 0
# Journey: J1
# Pages: P2 资源发现
# Consumer-faces: API (search_resources)
# Roles: ROLE_ORGAN_OPERATER
# Trace:
#   .testing/waves/wave-0-golden-path/features/j1-resource-discovery.feature
#   zw_brain/command/handlers/j1/data_search.py
#   zw_brain/domain/discovery_snapshot_projection.py
"""关键词搜索只展示已发布 active 资源（D53①）。

历史漏洞：data_search 的 API 资源枚举曾只 continue 掉 draft/revoked，放行了
待发布(approved_pending_publish)/审核中(pending_review)/已暂停(suspended)/
已过期(expired) 等未发布态——而快照发现路径用 _DISCOVERABLE_STATUSES={active}，
两条路口径不一致，能搜出未发布资源、点进去却不可申请的断头路。

本测试钉死：搜索结果只含 active；非 active 一律不出现在结果集。单一事实源 =
discovery_snapshot_projection.DISCOVERABLE_STATUSES（搜索侧 import 它，杜绝两处漂移）。
内存路径（无 DB）与 DB 路径共用同一 active 门，本测试覆盖内存路径的全部生命周期态。
"""
from __future__ import annotations

import pytest

from zw_brain.command.brain import BrainService
from zw_brain.command.handlers.j1.data_search import search_resources
from zw_brain.domain.discovery_snapshot_projection import DISCOVERABLE_STATUSES

pytestmark = pytest.mark.no_db

# 唯一查询令牌：注入的测试资源标题都含它，确保搜索结果只命中本测试资源、不被
# 种子库其它资源干扰（种子 api_resources 标题不含此令牌）。
_TOKEN = "活态过滤测试XZ9"

# 覆盖全部生命周期态各一条；只有 active 应被搜索放行。
_LIFECYCLE_FIXTURES = [
    ("active", "已发布态"),
    ("approved_pending_publish", "待发布态"),
    ("pending_review", "审核中态"),
    ("draft", "草稿态"),
    ("suspended", "已暂停态"),
    ("expired", "已过期态"),
    ("revoked", "已下线态"),
]


def _make_api_resource(status: str, label: str) -> dict:
    code = f"test-api-{status}"
    return {
        "resource_code": code,
        "title": f"{_TOKEN}_{label}",
        "owner_org_id": "11370000TEST00000A",
        "lifecycle_status": status,
        "resource_kind": "api",
        "summary_json": {"domain": "测试领域", "desc": f"{_TOKEN} 生命周期门测试资源"},
    }


@pytest.fixture()
def brain() -> BrainService:
    """纯内存 BrainService（无 DB）→ search_resources 走内存分支。"""
    b = BrainService()
    b._snapshot["api_resources"] = [_make_api_resource(s, lbl) for s, lbl in _LIFECYCLE_FIXTURES]
    return b


def test_search_returns_only_active_api_resources(brain: BrainService) -> None:
    """关键词命中本测试资源时，结果集只含 active，非 active 全部不出现。"""
    out = search_resources(brain, _TOKEN)
    statuses = {str(r.get("lifecycleStatus")) for r in out["results"] if _TOKEN in str(r.get("name", ""))}
    assert statuses == {"active"}, (
        f"搜索应只展示已发布 active 资源；实际命中态：{sorted(statuses)}"
    )


def test_search_excludes_each_non_active_status(brain: BrainService) -> None:
    """逐个生命周期态确认：除 active 外，每个非 active 资源都不在结果集（断头路根因）。"""
    out = search_resources(brain, _TOKEN)
    result_codes = {str(r.get("id")) for r in out["results"]}
    assert "test-api-active" in result_codes, "已发布资源应可被搜索到（正向对照）"
    for status, _label in _LIFECYCLE_FIXTURES:
        if status == "active":
            continue
        assert f"test-api-{status}" not in result_codes, (
            f"非 active 资源（{status}）不应出现在搜索结果——这正是「搜出未发布资源却不可申请」的断头路根因"
        )


def test_discoverable_statuses_is_active_only_single_source() -> None:
    """单一事实源不变量：搜索与发现共用的放行集合恒为「仅 active」（守 D53① 口径不被悄悄放宽）。"""
    assert DISCOVERABLE_STATUSES == frozenset({"active"})
