"""data_quality 脏值分类器守卫 — 锚定客户截图实证的脏值（测试 / 167 / 169,167 / 空）。

本测试是后端规则源（zw_brain/domain/data_quality.py）与前端镜像
（zw-brain-web/src/lib/dataQuality.ts）一致性的钉子：固定样例改一侧、另一侧必须跟改。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.data_quality import (
    MISSING_PURPOSE_LABEL,
    classify_purpose,
    is_dirty_purpose,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 客户 0604 截图实证脏值
        ("测试", "placeholder"),
        ("167", "numeric_only"),
        ("169,167", "numeric_only"),
        ("", "empty"),
        (None, "empty"),
        ("   ", "empty"),
        # 规则边界
        ("test", "placeholder"),
        ("无", "placeholder"),
        ("1", "placeholder"),
        ("12-3", "numeric_only"),
        ("169、167", "numeric_only"),
        ("X", "too_short"),
        # 合法用途（真实库高频值，不得误降级）
        ("行政依据", "clean"),
        ("业务协同", "clean"),
        ("用于数据校核", "clean"),
        ("工作参考", "clean"),
    ],
)
def test_classify_purpose(raw: str | None, expected: str) -> None:
    assert classify_purpose(raw) == expected


def test_is_dirty_purpose_matches_screenshot_dirty_set() -> None:
    for dirty in ["测试", "167", "169,167", "", None, "无", "1"]:
        assert is_dirty_purpose(dirty) is True
    for clean in ["行政依据", "业务协同", "用于数据校核"]:
        assert is_dirty_purpose(clean) is False


def test_missing_label_is_plain_language() -> None:
    # 降级文案天然过 R12：无工程术语 / 无 snake_case / 无 HTTP 码。
    assert MISSING_PURPOSE_LABEL == "未填写用途"
    for banned in ["projection", "package", "capability", "_", "404", "null", "None"]:
        assert banned not in MISSING_PURPOSE_LABEL
