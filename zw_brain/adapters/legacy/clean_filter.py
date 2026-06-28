"""`--only-clean` 导入过滤：判定一条 canonical 业务记录是否「符合 zw-brain 标准的干净数据」。

定位：历史 dump 含大量脏值（测试/未命名标题、纯数字/「测试」用途、缺机构、裸 id 当名字…），
全量导入后即便前端有渲染层兜底，演示/试用仍会零星露脏。`--only-clean` 在**导入时**把不达标的
业务记录跳过（不写库，从源头干净），跳过项由 mapper `stats.skip("<table>.unclean:<reason>")`
记账——**可审计、非静默**（承 D11 真实库回归：不是造假数据，是只收够格的真实数据）。

范围：仅业务记录（目录 catalog / 资源 resource / 申请 application）。治理基线
（机构 / 区划 / 字典 / actor）属基础设施，不在清洗范围（demo 仍需完整机构树与字典下拉）。

判据可调（GATE：什么算「干净」是业务标准）；当前默认见 is_clean_record。
"""

from __future__ import annotations

import re
from typing import Any

# 测试 / 占位 / 无意义名标记（与前端 isTestMarkerName、build_m0 候选评分同口径）。
_TEST_NAME_RE = re.compile(r"测试|test|ces|dhh|demo|未命名|样例|临时|无效|作废|待删|todo", re.I)
# 裸 hex / 长纯数字串当名字 = 无真实业务名。
_BARE_ID_RE = re.compile(r"^[0-9a-f]{16,}$|^\d{8,}$", re.I)
# 脏自由文本值：纯数字、纯标点、单字「测试」等（用于用途等字段）。
_DIRTY_VALUE_RE = re.compile(r"^\s*(测试|test|\d+|[,，;；.。、\-_/]+)\s*$", re.I)
# 占位机构名。
_PLACEHOLDER_DEPT = frozenset({"", "unknown", "未知", "申请部门", "无", "n/a", "na", "-"})


class SkipUnclean(Exception):
    """在 only_clean 模式下，某条记录不达标 → 由 mapper dispatch 捕获并记 stats.skip。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _blank(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def _bad_name(name: Any, code: Any = None) -> bool:
    n = str(name or "").strip()
    if not n:
        return True
    if code is not None and n == str(code).strip():
        return True  # name == code → 没有真实业务名，只有编码
    if _TEST_NAME_RE.search(n):
        return True
    if _BARE_ID_RE.match(n):
        return True
    return False


def _dirty_value(v: Any) -> bool:
    if v is None:
        return False  # 缺省不算脏（很多字段本就可空）；只拦「填了但是脏」。
    s = str(v).strip()
    if not s:
        return False
    return bool(_DIRTY_VALUE_RE.match(s))


def is_clean_record(kind: str, record: dict[str, Any]) -> tuple[bool, str]:
    """返回 (clean, reason)。reason 仅在 not clean 时有意义（喂给 stats.skip 记账）。

    record 是各 mapper 已抽好的关键字段子集（见各 _map_* 调用处），非完整 upsert payload。
    """
    if kind == "catalog":
        if _bad_name(record.get("name"), record.get("id")):
            return False, "catalog.bad_name"
        if _blank(record.get("provider")):
            return False, "catalog.no_provider"
        return True, ""
    if kind == "resource":
        if _bad_name(record.get("name"), record.get("id")):
            return False, "resource.bad_name"
        return True, ""
    if kind == "application":
        if _blank(record.get("resourceId")):
            return False, "application.no_resource_ref"
        if _bad_name(record.get("resource_name")):
            return False, "application.bad_resource_name"
        if str(record.get("applicantDept") or "").strip().lower() in _PLACEHOLDER_DEPT:
            return False, "application.placeholder_dept"
        for key in ("use_reason", "use_item", "other_reason"):
            if _dirty_value(record.get(key)):
                return False, f"application.dirty_{key}"
        return True, ""
    return True, ""  # 未知 kind 不拦（防御）
