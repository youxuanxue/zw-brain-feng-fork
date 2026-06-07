"""读路径资源类型折叠守卫（D53：只支持 库表/文件/API）。

存量库残留 legacy resource_kind='folder'/'url'/'link' 的行（归一化上线前导入），任何读路径
投影到消费面都必须经 canonical_resource_kind 折叠，否则 folder/url 泄漏到「资源类型」筛选/徽标
（违 D53 + R12 裸英文）。本测试钉死折叠表，防回潮。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.resource_kind import canonical_resource_kind


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 收敛三态原样
        ("table", "table"),
        ("file", "file"),
        ("api", "api"),
        # legacy 同义词折叠
        ("folder", "file"),
        ("url", "file"),
        ("link", "file"),
        ("service", "api"),
        # 大小写 / 空白容错
        ("FOLDER", "file"),
        ("  Url ", "file"),
        ("Service", "api"),
        # 空 / 未知 → None（读路径诚实空态，不臆造 table、不裸出英文）
        (None, None),
        ("", None),
        ("   ", None),
        ("mystery_kind", None),
        ("catalog_entry", None),
    ],
)
def test_canonical_resource_kind(raw: object, expected: str | None) -> None:
    assert canonical_resource_kind(raw) == expected


@pytest.mark.parametrize(
    ("res_type", "channel", "expected"),
    [
        # res_type 优先（存量极少有）
        ("api", "table", "api"),
        ("folder", None, "file"),
        # F3：res_type 缺供（62/64 行）→ 用交付渠道兜底推导，否则按钮永不分流
        (None, "service", "api"),
        (None, "table", "table"),
        (None, "file", "file"),
        (None, "folder", "file"),
        (None, "db", "table"),
        (None, "exchange", "table"),
        (None, "recurring_exchange", "table"),
        # 推不出（复合中文模式渠道）→ None（前端默认双按钮，安全）
        (None, "受控交付 + 审计回执", None),
        (None, None, None),
    ],
)
def test_delivery_resource_kind_channel_fallback(
    res_type: object, channel: object, expected: str | None
) -> None:
    from zw_brain.domain.services.delivery_service import _delivery_resource_kind

    assert _delivery_resource_kind(res_type, channel) == expected
