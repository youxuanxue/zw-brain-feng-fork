"""T5（6.4#5 目录详情字段）：信息资源格式 / 所属领域 裸码不泄漏到 UI（R12）。

走查实证：存量目录 resource_format 大量精确档外子码（0305/0203/0601…）、domain 回落 theme_group_id
裸码（"202,"）。读层须映射为可读标签或抑制，绝不把裸码送到详情。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.services.catalog_service import _readable_domain, _resource_format_label

pytestmark = pytest.mark.no_db


def test_format_exact_code():
    assert _resource_format_label("0200") == "库表"
    assert _resource_format_label("0400") == "接口"


def test_format_family_prefix_fallback():
    # 精确档外子码按 2 位族前缀回落到族标签（01 结构化 / 02 库表 / 03 非结构化 / 04 接口 / 05 链接）。
    assert _resource_format_label("0305") == "非结构化数据"
    assert _resource_format_label("0203") == "库表"
    assert _resource_format_label("0101") == "结构化数据"


def test_format_unmappable_returns_none_not_raw():
    # 06xx / 单字符等不可识别：返 None（R12 宁可不展示、绝不泄漏裸码）。
    assert _resource_format_label("0600") is None
    assert _resource_format_label("0") is None
    assert _resource_format_label("") is None
    assert _resource_format_label(None) is None


def test_domain_suppresses_bare_code():
    assert _readable_domain("", "202,") is None
    assert _readable_domain("301") is None
    assert _readable_domain("", "") is None


def test_domain_keeps_readable_name():
    assert _readable_domain("社会保障") == "社会保障"
    assert _readable_domain("", "民政服务") == "民政服务"
