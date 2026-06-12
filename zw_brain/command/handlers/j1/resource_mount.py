"""J2 资源挂接 handlers — 库表 / 文件 物化资源挂接（提交侧）。

补 Wave 1 挂数旅程缺的一半：此前 OPERATER 只能挂 API（resource_api.*），库表 / 文件
物化资源无创建入口（P5 资源挂接灰禁）。本模块补 `resource.mount.table.prepare` /
`resource.mount.file.prepare` 两个创建能力，产出 resource_kind=table/file 的草稿资产；
后续 submit_review → review → publish 复用既有 kind-agnostic 资产状态机（resource_api.py），
不新建复核/发布链。

诚实校验（设计即工作方式）：
- 库表：字段映射完整性真算（mapping_ready，操作员责任面）；provider 真实库连通性属
  上游缺供 → 记 connectivity="not_probed"，**绝不伪造"连接成功"**，发布激活时再校验。
- 文件：捕获内容指纹（content_fingerprint）作完整性锚。
- 库连接配置去敏（password/secret/token 不入库，仅留 host/port/database/table 等结构信息）。

边界守卫：
- owner_org 挂接后不可变（re-prepare 不能改 owner）。
- 跨 org 目录挂接拒（资源 owner_org 必须与目标目录 owner_org 一致）。
- 缺字段映射 → 允许存草稿、由 submit_review 守卫阻断（见 resource_api._submit_api_resource_review）。
"""

from __future__ import annotations

import hashlib
from typing import Any

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.errors import AccessDeniedError, InvalidStateError
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

# 库连接配置里属敏感、禁入库的键（去敏后只留结构信息）。
_CONNECTION_SECRET_KEYS = {"password", "passwd", "secret", "token", "ak", "sk", "access_key", "secret_key"}


def _access_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """共享/开放属性 → access_policy_json（B2，与 resource 详情 accessPolicy 同口径）。

    旧平台资源注册必填 共享类型/共享条件/开放类型/开放条件；落 access_policy_json 供
    资源详情/发现读路径回显。缺省值不伪造——None 由前端诚实空态承载。

    存储键 = ``share_type`` / ``share_condition``（0611 断点 C 修复，写读键统一）：
    与 legacy 导入 seed（adapters/legacy/mappers/catalog_metadata.py）和读端
    （discovery_snapshot_projection._share_type_by_resource / shared_type_for_resource）
    同键。此前写 ``shared_type`` 导致 UI 新挂的有条件资源回源失败、一律被判无条件，
    D55④ 受理→部门管理员审核两级在全新链路上永不触发。payload 入参键
    （``shared_type``/``shared_condition``）是挂接向导 API surface，保持不变。
    """
    return {
        "share_type": payload.get("shared_type"),
        "share_condition": payload.get("shared_condition"),
        "open_type": payload.get("open_type"),
        "open_condition": payload.get("open_condition"),
    }


def _business_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """资源注册业务信息 → summary_json 公共块（资源描述/来源系统/版本号/技术联系人/联系方式）。

    对标旧平台资源「基本信息」标签页（库表/文件资源详情对标截图）。table/file 共用。
    T4 补齐库表权威字段：资源所处位置 / 数据提供方式（周期·一次性）/ 资源更新周期——库表注册
    采集，文件注册不填则诚实 None；详情端「库表信息」回显（与采集端双向对齐）。
    """
    return {
        "resource_desc": payload.get("resource_desc"),
        "source_system": payload.get("source_system"),
        "resource_version": payload.get("resource_version"),
        "tech_contact": payload.get("tech_contact"),
        "contact_phone": payload.get("contact_phone"),
        "res_location": payload.get("res_location"),
        "data_provision_method": payload.get("data_provision_method"),
        "update_cycle": payload.get("update_cycle"),
    }


def _mappings_ready(field_mappings: Any) -> bool:
    """字段映射完整性：非空且每条都有 source + target。"""
    if not isinstance(field_mappings, list) or not field_mappings:
        return False
    for m in field_mappings:
        if not isinstance(m, dict):
            return False
        if not m.get("source") or not m.get("target"):
            return False
    return True


def _redact_connection(connection: Any) -> dict[str, Any]:
    """去敏库连接配置：丢弃 password/secret/token 类键，仅留结构信息。"""
    if not isinstance(connection, dict):
        return {}
    return {k: v for k, v in connection.items() if k.lower() not in _CONNECTION_SECRET_KEYS}


def _file_fingerprint(payload: dict[str, Any]) -> str:
    """文件内容指纹：优先用调用方提供的 content_hash，否则对 access_path+size 派生稳定锚。"""
    explicit = payload.get("content_hash") or payload.get("content_fingerprint")
    if explicit:
        return str(explicit)
    basis = f"{payload.get('access_path', '')}|{payload.get('file_name', '')}|{payload.get('size', '')}"
    return "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _guard_owner_immutable(deps: HandlerDeps, asset: dict[str, Any]) -> None:
    """owner_org 挂接后不可变：re-prepare 不能把已挂资源改到别的 owner。"""
    existing = deps.services.provider.find_api_resource(asset["resource_code"])
    if existing is None:
        return
    prev_owner = existing.get("owner_org_id")
    new_owner = asset.get("owner_org_id")
    if prev_owner and new_owner and prev_owner != new_owner:
        raise InvalidStateError(
            f"resource {asset['resource_code']} owner_org 已挂接为 {prev_owner}，不可改为 {new_owner}"
        )


def _guard_catalog_same_org(deps: HandlerDeps, asset: dict[str, Any]) -> None:
    """跨 org 目录挂接拒：当目标目录有归属 org 时，挂接资源声明的 owner_org **必须等于**目录 owner。

    结构一致性守卫（非完整 authz——owner_org 仍是调用方自报，真正的「调用者属哪个 org」由 C1
    写边界另解）。但本守卫对 owner **缺省也拒**（不再 skip-if-no-owner），堵掉「省略 owner_org
    绕过跨 org 校验」的口子：目录有 owner 时，未声明归属或归属不符一律拒。目录不可解析 / 目录本身
    无 owner 时跳过（不伪造拒绝）。
    """
    catalog_code = asset.get("catalog_code")
    if not catalog_code:
        return
    entry = deps.repos.catalog.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
    cat_owner = getattr(entry, "owner_org_id", None) if entry is not None else None
    if not cat_owner:
        return  # 目录无归属 org（不可解析）→ 跳过
    owner = asset.get("owner_org_id")
    if owner != cat_owner:
        raise AccessDeniedError(
            f"挂接资源 owner_org={owner!r} 必须与目标目录 {catalog_code} 的 owner_org={cat_owner!r} "
            f"一致（跨 org 或未声明归属一律拒）"
        )


def _prepare_table(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> dict[str, Any]:
    resource_code = str(payload["resource_code"])
    field_mappings = payload.get("field_mappings") or []
    mapping_ready = _mappings_ready(field_mappings)
    summary = {
        "title": payload.get("title", resource_code),
        "materialization": "table",
        "table_name": payload.get("table_name"),
        "connection_ref": _redact_connection(payload.get("connection")),
        "field_mappings": field_mappings,
        "mapping_ready": mapping_ready,
        # 诚实：provider 真实库连通性属上游缺供，发布激活时校验，不在挂接期伪造成功。
        "connectivity": "not_probed",
        # B2：资源注册业务信息（资源描述/来源系统/版本号/技术联系人/联系方式）。
        **{k: v for k, v in _business_summary(payload).items() if v is not None},
    }
    asset = deps.services.provider.asset_payload(
        {**payload, "summary_json": summary, "access_policy_json": _access_policy(payload)},
        kind="table",
        default_status="draft",
    )
    _guard_owner_immutable(deps, asset)
    _guard_catalog_same_org(deps, asset)

    connection = _redact_connection(payload.get("connection"))
    binding = {
        "binding_code": f"{resource_code}#table",
        "resource_code": resource_code,
        "channel_kind": "table",
        "route_ref": payload.get("table_name"),
        "endpoint_ref": {
            "table_name": payload.get("table_name"),
            "schema_name": connection.get("database"),
        },
        "lifecycle_status": "draft",
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        result = deps.services.provider.upsert_api_resource(asset)
        # 写库表分型 binding，让资源详情「库表信息」（typed_resource_detail._table_section）有值。
        deps.services.provider.upsert_api_binding(binding)
        deps.append_audit_feed("resource.mount.table.prepare", resource_code, "ok", actor)
        return result | {
            "audit_id": audit_id,
            "mapping_ready": mapping_ready,
            "connectivity": "not_probed",
        }

    return deps.write(ctx, asset, mutation)


def _prepare_file(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> dict[str, Any]:
    resource_code = str(payload["resource_code"])
    fingerprint = _file_fingerprint(payload)
    summary = {
        "title": payload.get("title", resource_code),
        "materialization": "file",
        "file_name": payload.get("file_name"),
        "access_path": payload.get("access_path"),
        "content_fingerprint": fingerprint,
        "update_frequency": payload.get("update_frequency"),
        # B2：文件采集端补 格式/大小/存储类型 → 与详情端 _file_section 对齐（采集→展示同字段）。
        "file_format": payload.get("file_format"),
        "file_size": payload.get("file_size"),
        "file_store_type": payload.get("file_store_type"),
        # B2：资源注册业务信息。
        **{k: v for k, v in _business_summary(payload).items() if v is not None},
    }
    asset = deps.services.provider.asset_payload(
        {**payload, "summary_json": summary, "access_policy_json": _access_policy(payload)},
        kind="file",
        default_status="draft",
    )
    _guard_owner_immutable(deps, asset)
    _guard_catalog_same_org(deps, asset)

    # 文件分型 binding：detail 端 _file_section 从 endpoint_ref(file_name/file_format/
    # file_store_type) + schema_ref(file_size) 读，故采集端在此把它们写进 binding，
    # 让「文件信息」标签页不再永远空态（B2 修复点）。
    binding = {
        "binding_code": f"{resource_code}#file",
        "resource_code": resource_code,
        "channel_kind": "file",
        "route_ref": payload.get("file_name") or payload.get("access_path"),
        "endpoint_ref": {
            "file_name": payload.get("file_name"),
            "file_format": payload.get("file_format"),
            "file_store_type": payload.get("file_store_type"),
        },
        "schema_ref": {"file_size": payload.get("file_size")},
        "lifecycle_status": "draft",
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        result = deps.services.provider.upsert_api_resource(asset)
        deps.services.provider.upsert_api_binding(binding)
        deps.append_audit_feed("resource.mount.file.prepare", resource_code, "ok", actor)
        return result | {"audit_id": audit_id, "content_fingerprint": fingerprint}

    return deps.write(ctx, asset, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Dispatch entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_resource_mount_table_prepare(
    deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]
) -> Any:
    return _prepare_table(deps, ctx, payload)


def handler_resource_mount_file_prepare(
    deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]
) -> Any:
    return _prepare_file(deps, ctx, payload)
