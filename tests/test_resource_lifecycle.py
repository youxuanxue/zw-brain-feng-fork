"""resource_lifecycle 单一事实源 — 机器值 → 中文展示态投影（D53①）。

护住三件事：active=已发布（反转旧词「可复用」）、未知值诚实原样返回（不臆造）、
with_lifecycle_label 只在携带 lifecycle_status 时补 label（不污染无关 dict）。
"""
from __future__ import annotations

import pytest

from zw_brain.domain.resource_lifecycle import lifecycle_label, with_lifecycle_label

pytestmark = pytest.mark.no_db


def test_active_is_published_not_reusable() -> None:
    # D53①：active 对需求方语义 = 已发布；旧词「可复用」已退役。
    assert lifecycle_label("active") == "已发布"


def test_known_lifecycle_values_have_labels() -> None:
    assert lifecycle_label("approved_pending_publish") == "待发布"
    assert lifecycle_label("pending_review") == "审核中"
    assert lifecycle_label("pending_platform_review") == "平台审核中"
    assert lifecycle_label("draft") == "草稿"
    assert lifecycle_label("revoked") == "已下线"


def test_unknown_value_returns_itself_honestly() -> None:
    # 不臆造——未知/空值原样返回，让缺口浮出而非被假标签掩盖。
    assert lifecycle_label("some_future_state") == "some_future_state"
    assert lifecycle_label("") == ""
    assert lifecycle_label(None) == ""


def test_with_lifecycle_label_injects_only_when_status_present() -> None:
    out = with_lifecycle_label({"catalog_code": "c1", "lifecycle_status": "draft"})
    assert out["lifecycle_label"] == "草稿"
    # 无 lifecycle_status 的 dict 不被污染。
    untouched = with_lifecycle_label({"catalog_code": "c1"})
    assert "lifecycle_label" not in untouched
