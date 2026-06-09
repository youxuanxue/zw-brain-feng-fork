"""Typed resource detail projection (反馈 6 — 按资源类型分型).

旧平台「资源维护」按资源类型展示不同详情：库表资源看表/字段、文件资源看文件信息
（文件名/类型/大小/存储类型）、文件夹资源面向文件夹、接口资源看服务化信息
（服务地址/参数）。我们的导入把这些类型化事实落进 ``resource_asset.resource_kind``
与 ``resource_channel_binding`` 的 ``endpoint_ref`` / ``schema_ref`` / ``route_ref``，
本模块把它们投影为前端可直接渲染的「分型详情块」，不复刻旧表单形态、只继承字段契约。

读路径专用（纯投影，不写库）。给定 focused 资源的 asset dict + 该资源的 binding dicts，
产出 ``typedDetail = {kind, kindLabel, sections:[{title, rows:[{label,value}]}]}``，
``rows`` 已是「label → value（缺则 None，前端诚实空态）」，调用方不再二次解析。
"""
from __future__ import annotations

from typing import Any

from zw_brain.domain.resource_labels import UPDATE_CYCLE_LABELS as _UPDATE_CYCLE_LABELS
from zw_brain.domain.resource_labels import summary_body as _summary_body

# resource_kind → 政务白话物化形态（R12：禁工程术语，纯中文）。
# 资源类型收敛为「库表 / 文件 / API」（D53）——文件夹/链接退役，归一化已折叠为 file。
KIND_LABELS: dict[str, str] = {
    "table": "库表",
    "file": "文件",
    "api": "接口",
    "service": "接口",
}

# file_store_type 旧平台枚举 → 中文（centerStore=中心库存储 等）。
_FILE_STORE_LABELS: dict[str, str] = {
    "centerStore": "中心库存储",
    "localStore": "本地存储",
    "objectStore": "对象存储",
}

# 数据提供方式枚举 → 中文（采集端 DATA_PROVISION_OPTIONS 同口径，T4）。
# 注：前后端各一份是 FE/BE 语言边界的固有投影（catalogCompileFields 已注明「同口径」），非同进程重复。
_DATA_PROVISION_LABELS: dict[str, str] = {
    "periodic": "周期提供",
    "one_time": "一次性提供",
}

# 资源更新周期 / summary 解包：单源在 resource_labels（与 catalog_service 同 import，消同进程重复）。


def _row(label: str, value: Any) -> dict[str, Any]:
    """单行 label → value；空值统一归一到 None，前端渲染「未提供」诚实空态。"""
    if value is None or value == "" or value == []:
        return {"label": label, "value": None}
    return {"label": label, "value": str(value)}


def _file_size_label(raw: Any) -> Any:
    """字节数 → 人类可读（KB/MB）。非数字原样返回。"""
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return raw
    if size <= 0:
        return None
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def _first_binding(bindings: list[dict[str, Any]], *, channel_kind: str | None = None) -> dict[str, Any]:
    """取第一条（可按 channel_kind 过滤）binding；无则空 dict。"""
    for binding in bindings:
        if channel_kind is None or binding.get("channel_kind") == channel_kind:
            return binding
    return {}


_UPDATE_FREQUENCY_LABELS: dict[str, str] = {
    "realtime": "实时",
    "daily": "每日",
    "weekly": "每周",
    "monthly": "每月",
}


def _file_section(bindings: list[dict[str, Any]], summary: Any = None) -> dict[str, Any]:
    """文件 / 文件夹资源：文件信息（文件名/文件类型/文件大小/存储类型/更新频率）。

    旧平台文件资源详情 = 基本信息 + 文件信息。文件级事实落在 channel binding 的
    endpoint_ref（file_name/file_format/file_store_type）与 schema_ref（file_size）；
    更新频率落在资源 summary_json（采集端 updateFrequency，T4 对齐回显）。
    """
    binding = _first_binding(bindings, channel_kind="file") or _first_binding(bindings)
    endpoint = binding.get("endpoint_ref") or {}
    schema = binding.get("schema_ref") or {}
    body = _summary_body(summary)
    file_name = endpoint.get("file_name") or schema.get("file_name") or binding.get("route_ref")
    file_format = endpoint.get("file_format") or schema.get("file_format")
    store_type = endpoint.get("file_store_type")
    store_label = _FILE_STORE_LABELS.get(str(store_type), store_type)
    update_freq = body.get("update_frequency") or endpoint.get("update_frequency")
    return {
        "title": "文件信息",
        "rows": [
            _row("文件名称", file_name),
            _row("文件类型", file_format),
            _row("文件大小", _file_size_label(schema.get("file_size"))),
            _row("存储类型", store_label),
            _row("更新频率", _UPDATE_FREQUENCY_LABELS.get(str(update_freq), update_freq) if update_freq else None),
        ],
    }


def _table_section(bindings: list[dict[str, Any]], summary: Any = None) -> dict[str, Any]:
    """库表资源：物理表信息（表名/所属库/表版本）+ 注册业务字段（资源所处位置/数据提供方式/
    资源更新周期，T4）。字段级清单由 catalogFields/字段模型块承载。

    所属库优先取有意义的 schema_name；旧库只存 database_id（裸 UUID）时不展示噪声
    （宁缺毋滥，UUID 对用户无信息量）。业务字段取 summary_json，缺则诚实空态（_row → None）。
    """
    binding = _first_binding(bindings, channel_kind="table") or _first_binding(bindings)
    endpoint = binding.get("endpoint_ref") or {}
    schema = binding.get("schema_ref") or {}
    body = _summary_body(summary)
    provision = body.get("data_provision_method")
    update_cycle = body.get("update_cycle")
    return {
        "title": "库表信息",
        "rows": [
            _row("物理表名", endpoint.get("table_name") or schema.get("table_name") or binding.get("route_ref")),
            _row("所属库", endpoint.get("schema_name")),
            _row("表版本", schema.get("table_version")),
            _row("资源所处位置", body.get("res_location")),
            _row("数据提供方式", _DATA_PROVISION_LABELS.get(str(provision), provision) if provision else None),
            _row("资源更新周期", _UPDATE_CYCLE_LABELS.get(str(update_cycle), update_cycle) if update_cycle else None),
        ],
    }


def _api_section(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """接口资源：服务化信息（服务地址/接口标识）。对齐旧平台「代理服务详情」。"""
    binding = _first_binding(bindings, channel_kind="api_gateway") or _first_binding(bindings)
    endpoint = binding.get("endpoint_ref") or {}
    return {
        "title": "接口信息",
        "rows": [
            _row("服务地址", binding.get("route_ref") or endpoint.get("api_path")),
            _row("接口标识", endpoint.get("api_id")),
            _row("接入通道", "接口代理服务" if binding else None),
        ],
    }


def typed_resource_detail(
    *,
    resource_kind: str | None,
    bindings: list[dict[str, Any]],
    summary: Any = None,
) -> dict[str, Any]:
    """按 resource_kind 选分型模板，产出该类型独有的详情块。

    返回 ``{kind, kindLabel, sections:[...]}``；sections 至少 1 块（缺数据时块仍在、
    rows value=None 诚实空态，绝不造假数据 D11）。未知 kind 回退库表模板。
    ``summary`` = focused 资源的 summary_json，承载注册业务字段（T4：库表的资源所处位置/
    数据提供方式/资源更新周期）。
    """
    kind = str(resource_kind or "table").lower()
    # 资源类型收敛为 库表/文件/API（D53）：folder/url 已在归一化折叠为 file；
    # 此处对任何残留 folder/url 也防御性归入文件分型（canonical=file），不再单列。
    if kind in {"api", "service"}:
        section = _api_section(bindings)
        canonical = "api"
    elif kind in {"file", "folder", "url"}:
        section = _file_section(bindings, summary)
        canonical = "file"
    else:
        section = _table_section(bindings, summary)
        canonical = "table"
    return {
        "kind": canonical,
        "kindLabel": KIND_LABELS.get(canonical, KIND_LABELS.get(kind, "库表")),
        "sections": [section],
    }
