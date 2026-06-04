"""数据质量分类器 — 真实导入单「用途/使用事由」脏值的机械化判定（单一规则源）。

客户试用反馈（0604，业务方试用反馈 + 截图实证）：真实导入申请单的「用途」列出现「测试」「167」
「169,167」这类脏值裸奔在需方/办理视图。乔布斯裁决（本组）：

  1) 列表渲染时脏值**降级显示**（「未填写用途」次要样式），不让噪音污染需方视图；
  2) 「用途缺失/无效」的单子计入**供方数据质量队列**（数据质量是供方的待办，不是需方的噪音）。

本模块是「什么算脏值」的**唯一规则源**（Python 权威 + 前端 dataQuality.ts 镜像 +
tests/test_data_quality_classifier.py 守一致）。规则机械化，不靠散文：

  - 空 / 纯空白              → empty
  - 纯数字 / 数字+分隔符      → numeric_only（如 "167" "169,167" "12-3"）
  - 占位测试词（枚举）        → placeholder（如 "测试" "test" "demo" "无" "暂无" "1"）
  - 过短（去空白后 < 2 字符）  → too_short

任一非空类目 → 视为脏值（``is_dirty`` True），列表降级 + 进供方质量队列。
"""

from __future__ import annotations

import re

__all__ = [
    "classify_purpose",
    "is_dirty_purpose",
    "purpose_from_payload",
    "MISSING_PURPOSE_LABEL",
]

# 列表降级文案（政务白话，天然过 R12：无工程术语 / 无 snake_case / 无 HTTP 码）。
MISSING_PURPOSE_LABEL = "未填写用途"

# 占位/测试词枚举（去空白 + 转小写后精确匹配）。保持克制——只收真见过的占位串，
# 避免误伤合法短用途。新增脏值类型优先扩这里或下面的规则，不在调用方散落 if。
_PLACEHOLDER_TOKENS: frozenset[str] = frozenset(
    {
        "测试",
        "test",
        "测试数据",
        "demo",
        "演示",
        "无",
        "暂无",
        "待填",
        "待补充",
        "n/a",
        "na",
        "null",
        "none",
        "-",
        "—",
        "1",
        "0",
    }
)

# 纯数字 / 数字 + 常见分隔符（逗号 / 顿号 / 横线 / 斜杠 / 点 / 空格）。
_NUMERIC_ONLY = re.compile(r"^[\d\s,，、\-/\.]+$")


def classify_purpose(raw: str | None) -> str:
    """返回脏值类目：clean | empty | numeric_only | placeholder | too_short。

    clean = 合法用途（不降级）；其余 = 脏值（降级 + 进供方质量队列）。
    """
    text = (raw or "").strip()
    if not text:
        return "empty"
    lowered = text.lower()
    if lowered in _PLACEHOLDER_TOKENS:
        return "placeholder"
    if _NUMERIC_ONLY.match(text):
        return "numeric_only"
    # 去掉所有空白后长度 < 2（如单字符残值），视为信息量不足。
    if len(re.sub(r"\s+", "", text)) < 2:
        return "too_short"
    return "clean"


def is_dirty_purpose(raw: str | None) -> bool:
    """脏值判定：任一非 clean 类目 → True（列表降级 + 计入供方质量队列）。"""
    return classify_purpose(raw) != "clean"


def purpose_from_payload(payload: dict | None) -> str:
    """application_record.payload_json → 原始用途文本（多 legacy 字段名兜底，口径单源）。

    与 discovery_snapshot_projection / workbench_backlog_projection 共用，避免两处
    各写一遍字段兜底序导致脏值计数口径漂移。
    """
    p = payload or {}
    return str(
        p.get("purpose") or p.get("use_reason") or p.get("apply_basis") or p.get("use_item") or ""
    )
