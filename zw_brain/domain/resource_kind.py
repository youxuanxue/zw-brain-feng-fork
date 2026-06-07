"""资源类型（物化形态）读路径归一 — 单一事实源（D53：只支持 库表/文件/API）。

`adapters/legacy/mappers/_normalize_resource_kind` 在**入库闸门**折叠（写侧）；本模块是**读路径**
防御兜底：存量库里仍残留 legacy `resource_kind='folder'/'url'/'link'` 的行（在归一化上线前导入），
任何把 stored kind 投影到消费面（发现卡 / 资源详情 / 搜索结果 / 交付分流）的读路径都必须经此折叠，
否则 folder/url 会泄漏到「资源类型」筛选、徽标与详情分型（违 D53 + R12 裸英文）。
"""

from __future__ import annotations

from typing import Any

# legacy 同义词 → 收敛后的物化形态（D53）。文件夹/链接退役并入文件；service 是 API 的历史别名。
_READ_KIND_FOLD = {"folder": "file", "url": "file", "link": "file", "service": "api"}
_CANONICAL_KINDS = frozenset({"table", "file", "api"})


def canonical_resource_kind(raw: Any) -> str | None:
    """折叠任意 stored resource_kind 到 库表/文件/API；空/未知→None（读路径不臆造 table，诚实空态）。

    - folder/url/link → file，service → api，table/file/api 原样；
    - None / 空串 / 未知 token → None（消费面不渲染徽标/筛选项，绝不裸出 legacy 英文）。
    """
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    text = _READ_KIND_FOLD.get(text, text)
    return text if text in _CANONICAL_KINDS else None
