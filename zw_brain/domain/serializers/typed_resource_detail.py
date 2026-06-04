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

# resource_kind → 政务白话物化形态（R12：禁工程术语，纯中文）。
KIND_LABELS: dict[str, str] = {
    "table": "库表",
    "file": "文件",
    "folder": "文件夹",
    "api": "接口",
    "service": "接口",
    "url": "链接",
}

# file_store_type 旧平台枚举 → 中文（centerStore=中心库存储 等）。
_FILE_STORE_LABELS: dict[str, str] = {
    "centerStore": "中心库存储",
    "localStore": "本地存储",
    "objectStore": "对象存储",
}


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


def _file_section(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """文件 / 文件夹资源：文件信息（文件名/文件类型/文件大小/存储类型）。

    旧平台文件资源详情 = 基本信息 + 文件信息。文件级事实落在 channel binding 的
    endpoint_ref（file_name/file_format/file_store_type）与 schema_ref（file_size）。
    """
    binding = _first_binding(bindings, channel_kind="file") or _first_binding(bindings)
    endpoint = binding.get("endpoint_ref") or {}
    schema = binding.get("schema_ref") or {}
    file_name = endpoint.get("file_name") or schema.get("file_name") or binding.get("route_ref")
    file_format = endpoint.get("file_format") or schema.get("file_format")
    store_type = endpoint.get("file_store_type")
    store_label = _FILE_STORE_LABELS.get(str(store_type), store_type)
    return {
        "title": "文件信息",
        "rows": [
            _row("文件名称", file_name),
            _row("文件类型", file_format),
            _row("文件大小", _file_size_label(schema.get("file_size"))),
            _row("存储类型", store_label),
        ],
    }


def _table_section(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """库表资源：物理表信息（表名/所属库/表版本）。字段级清单由 catalogFields/字段模型块承载。

    所属库优先取有意义的 schema_name；旧库只存 database_id（裸 UUID）时不展示噪声
    （宁缺毋滥，UUID 对用户无信息量）。
    """
    binding = _first_binding(bindings, channel_kind="table") or _first_binding(bindings)
    endpoint = binding.get("endpoint_ref") or {}
    schema = binding.get("schema_ref") or {}
    return {
        "title": "库表信息",
        "rows": [
            _row("物理表名", endpoint.get("table_name") or schema.get("table_name") or binding.get("route_ref")),
            _row("所属库", endpoint.get("schema_name")),
            _row("表版本", schema.get("table_version")),
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


def _url_section(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """链接资源：外链信息（链接名称/链接说明）。"""
    binding = _first_binding(bindings, channel_kind="url") or _first_binding(bindings)
    endpoint = binding.get("endpoint_ref") or {}
    return {
        "title": "链接信息",
        "rows": [
            _row("链接名称", endpoint.get("url_name") or binding.get("route_ref")),
            _row("链接说明", endpoint.get("url_description")),
        ],
    }


def typed_resource_detail(
    *,
    resource_kind: str | None,
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    """按 resource_kind 选分型模板，产出该类型独有的详情块。

    返回 ``{kind, kindLabel, sections:[...]}``；sections 至少 1 块（缺数据时块仍在、
    rows value=None 诚实空态，绝不造假数据 D11）。未知 kind 回退库表模板。
    """
    kind = str(resource_kind or "table").lower()
    if kind in {"api", "service"}:
        section = _api_section(bindings)
        canonical = "api"
    elif kind == "file" or kind == "folder":
        section = _file_section(bindings)
        canonical = kind
    elif kind == "url":
        section = _url_section(bindings)
        canonical = "url"
    else:
        section = _table_section(bindings)
        canonical = "table"
    return {
        "kind": canonical,
        "kindLabel": KIND_LABELS.get(canonical, KIND_LABELS.get(kind, "库表")),
        "sections": [section],
    }
