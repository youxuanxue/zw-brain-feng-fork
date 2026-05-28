#!/usr/bin/env python3
"""一次性构建 M0 sd-default 真实数据迁移所需 3 张 manifest fixture：
  - iaf-binding-manifest.json         : pub_user.ID → synthetic iaf-sub (M0 首登前占位)
  - role-mapping-manifest.json        : 73 legacy ROLE_* → 6 个产品 BUSINESS_ROLE_CODES
  - capability-mapping-manifest.json  : pub_resource.ID → capability_id（按 URL 前缀匹配 + 仅收录已注册 Skill）

源数据：old/10示例数据/dump-dsp_bsp-202604271139.sql（脱敏样例，作为 sd-default M0 基线）。

定位（important）：本脚本输出的不是"自动决策"，而是 **团队协作下 M0 实施工程师的工作产物 baseline**。
角色映射的语义判定 + capability 收录范围必须由业务方在现场最终确认。复跑前清空旧 fixture。

用法::
  uv run python scripts/build_m0_sd_default_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DUMP = REPO_ROOT / "old/10示例数据/dump-dsp_bsp-202604271139.sql"
OUT = REPO_ROOT / "tests/fixtures/m0-sd-default"

# ---------------------------------------------------------------------------
# 73 legacy ROLE_* → 6 产品 BUSINESS_ROLE_CODES 的人工映射。
# 不在映射表内的 legacy role：mapper fail-closed 留 missing_role_mapping issue。
# tag_lead_dept：标签位（D-decision R14 fix），仅对"牵头部门" 系列绑定。
# ---------------------------------------------------------------------------
ROLE_MAPPING: list[tuple[str, str, str, str | None, str]] = [
    # legacy_ref, target_type, target_role_code, target_tag, rationale
    # —— 直接同名 ——
    ("ROLE_BUSIAUDIT", "role", "ROLE_BUSIAUDIT", None, "运营管理人员直接对齐"),
    ("ROLE_ORGAN_MANAGER", "role", "ROLE_ORGAN_MANAGER", None, "部门管理员直接对齐"),
    ("ROLE_ORGAN_OPERATER", "role", "ROLE_ORGAN_OPERATER", None, "部门操作员直接对齐"),
    ("ROLE_SYSTEM", "role", "ROLE_SYSTEM", None, "系统运维人员直接对齐"),
    # —— 业务岗位 ——
    ("ROLE_BUSINESS_MANAGER", "role", "ROLE_ORGAN_MANAGER", None, "业务管理人员 = 部门管理员的语义同义词"),
    ("ROLE_BUSINESS_OPERATOR", "role", "ROLE_ORGAN_OPERATER", None, "业务实施人员"),
    ("ROLE_BUSINESS_PROVIDED", "role", "ROLE_ORGAN_MANAGER", None, "提供方部门业务管理"),
    ("ROLE_BUSIOPER", "role", "ROLE_BUSIAUDIT", None, "运营业务人员（平台主管部门职能）"),
    ("ROLE_BUS_MANAGER_TEST", "role", "ROLE_BUSIAUDIT", None, "数据主管部门"),
    ("ROLE_CONTENT_CHECKER", "role", "ROLE_BUSIAUDIT", None, "内容审核员（平台复核职能）"),
    ("ROLE_CONTENT_EDITOR", "role", "ROLE_ORGAN_OPERATER", None, "内容编辑（部门内编制职能）"),
    ("ROLE_RESOURCEAPPLY", "role", "ROLE_ORGAN_OPERATER", None, "资源申请人员"),
    ("ROLE_RESOURCEPUB", "role", "ROLE_BUSIAUDIT", None, "资源发布者（平台发布权）"),
    ("ROLE_RESOURCE_MANAGER", "role", "ROLE_ORGAN_MANAGER", None, "资源管理人员"),
    ("ROLE_RESOURCE_OPERTOR", "role", "ROLE_ORGAN_OPERATER", None, "资源操作人员"),
    ("ROLE_PUBAUDIT", "role", "ROLE_BUSIAUDIT", None, "发布审核员"),
    ("ROLE_USEAUDIT", "role", "ROLE_ORGAN_MANAGER", None, "资源授权审批"),
    ("ROLE_submission", "role", "ROLE_ORGAN_OPERATER", None, "需求提报员"),
    ("ROLE_Community", "role", "ROLE_ORGAN_OPERATER", None, "社区填报者"),
    ("ROLE_ROW", "role", "ROLE_ORGAN_OPERATER", None, "街道填报者"),
    ("ROLE_Supervisor", "role", "ROLE_BUSIAUDIT", None, "大数据主管管理部门"),
    ("ROLE_WORKER", "role", "ROLE_ORGAN_OPERATER", None, "工作人员"),
    ("ROLE_WORKER_APP", "role", "ROLE_ORGAN_OPERATER", None, "基层工作人员"),
    # —— 数据治理 / 领导 ——
    ("ROLE_DATA_LEADER", "role", "ROLE_ORGAN_MANAGER", "tag_lead_dept", "数据领导（牵头部门）"),
    ("ROLE_DATA_LEADER_APP", "role", "ROLE_ORGAN_MANAGER", "tag_lead_dept", "基层数据领导"),
    ("ROLE_DATA_MANAGE_TEAM", "role", "ROLE_BUSIAUDIT", None, "数据治理团队"),
    ("ROLE_LEADAUDIT", "role", "ROLE_BUSIAUDIT", "tag_lead_dept", "牵头部门审核员"),
    ("ROLE_LEADDEPT", "role", "ROLE_ORGAN_OPERATER", "tag_lead_dept", "牵头部门操作员"),
    ("ROLE_MGMT_LEADER", "role", "ROLE_ORGAN_MANAGER", None, "分管领导"),
    ("ROLE_MGMT_LEADER_APP", "role", "ROLE_ORGAN_MANAGER", None, "基层分管领导"),
    # —— 部门管理员系列 ——
    ("ROLE_ORGAN", "role", "ROLE_ORGAN_MANAGER", None, "部门管理员"),
    # —— 安全 ——
    ("ROLE_AUDIT", "role", "ROLE_SECURITY_AUDIT", None, "安全审计人员"),
    ("ROLE_SECURITY_AUDITOR", "role", "ROLE_SECURITY_AUDIT", None, "安全审计员"),
    ("ROLE_SECURITY_MANAGER", "role", "ROLE_SECURITY_ADMIN", None, "安全管理员"),
    ("ROLE_SECRET", "role", "ROLE_SECURITY_ADMIN", None, "安全保密人员"),
    # —— 运维 ——
    ("ROLE_MAINTEN", "role", "ROLE_SYSTEM", None, "运维管理人员"),
    ("ROLE_FIRST_OPERATION", "role", "ROLE_SYSTEM", None, "一线运维"),
    ("ROLE_GDRP_OPS_ADMIN", "role", "ROLE_SYSTEM", None, "运维管理员"),
    ("ROLE_GDRP_OPS_WORKER", "role", "ROLE_SYSTEM", None, "运维普通用户"),
    ("ROLE_MANAGER", "role", "ROLE_SYSTEM", None, "系统管理人员"),
    # —— 区域 ——
    ("ROLE_REGION", "role", "ROLE_ORGAN_MANAGER", None, "地市管理员"),
    ("ROLE_REGION_ADMIN", "role", "ROLE_ORGAN_MANAGER", None, "基层区域管理员"),
    ("ROLE_REGION_ALL", "role", "ROLE_ORGAN_MANAGER", None, "区域管理员（本级及以下）"),
    ("ROLE_REGION_SELF", "role", "ROLE_ORGAN_MANAGER", None, "区域管理员（本级）"),
    ("ROLE_COUNTRY_ADMIN", "role", "ROLE_ORGAN_MANAGER", None, "区县管理员"),
    # —— 政务平台 ——
    ("ROLE_ZJPT_QXBMGLY", "role", "ROLE_ORGAN_MANAGER", None, "区县部门管理员"),
    ("ROLE_ZJPT_QXBMPTYH", "role", "ROLE_ORGAN_OPERATER", None, "区县部门普通用户"),
    ("ROLE_ZJPT_SJBMGLY", "role", "ROLE_ORGAN_MANAGER", None, "市部门管理员"),
    ("ROLE_ZJPT_SJBMPTYH", "role", "ROLE_ORGAN_OPERATER", None, "市部门普通用户"),
    ("ROLE_ZJPT_SQCZY", "role", "ROLE_ORGAN_OPERATER", None, "社区操作员"),
    ("ROLE_ZJPT_SQGLY", "role", "ROLE_ORGAN_MANAGER", None, "社区管理员"),
    ("ROLE_ZJPT_WGCZY", "role", "ROLE_ORGAN_OPERATER", None, "网格操作员"),
    ("ROLE_ZJPT_WGGLY", "role", "ROLE_ORGAN_MANAGER", None, "网格管理员"),
    ("ROLE_ZJPT_ZJCZY", "role", "ROLE_ORGAN_OPERATER", None, "镇街操作员"),
    ("ROLE_ZJPT_ZJGLY", "role", "ROLE_ORGAN_MANAGER", None, "镇街管理员"),
    # —— 开放门户（与共享门户角色等价，仅 surface 不同）——
    ("ROLE_OPEN_BUSIADMIN", "role", "ROLE_BUSIAUDIT", None, "运营管理人员（开放门户）"),
    ("ROLE_OPEN_BUSIOPER", "role", "ROLE_BUSIAUDIT", None, "运营业务人员（开放）"),
    ("ROLE_OPEN_CHECKER", "role", "ROLE_BUSIAUDIT", None, "部门审核员（开放）"),
    ("ROLE_OPEN_DEPTADMIN", "role", "ROLE_ORGAN_MANAGER", None, "部门管理员（开放）"),
    ("ROLE_OPEN_MANAGER", "role", "ROLE_SYSTEM", None, "系统管理员（开放）"),
    ("ROLE_OPEN_OPERATOR", "role", "ROLE_ORGAN_OPERATER", None, "部门操作员（开放）"),
    ("ROLE_OPEN_REGIONADMIN", "role", "ROLE_ORGAN_MANAGER", None, "地市管理员（开放）"),
    ("ROLE_OPEN_SYSTEM", "role", "ROLE_SYSTEM", None, "系统运维人员（开放）"),
    # —— 显式不映射（business decision，非技术问题）——
    # 旧平台技术角色 / 多租户 / 工单系统遗留，未在 zw-brain 7 角色矩阵承接：
    #   ROLE_APP_DEVELOPER / ROLE_SUPER / ROLE_SUPER_ADMIN — 技术/超管
    #   TENANT_ADMIN / TENANT_DEVELOPER — 多租户残留
    #   ROLE_INTEGRATION_ACCEPTER/CREATOR/EXECUTOR — 工单系统（zw-brain 用异议替代）
    #   ROLE_SITE_MESSAGE_RECEIVER — 站内信（外部消息中心）
    #   ROLE_GDRP_BUSINESS_TAG — 数据治理标签管理（外部数据治理中心）
    # 这些 legacy_ref 不出现在 manifest，mapper 记 missing_role_mapping issue，
    # 对应用户的 binding 留空（如果该用户 ONLY 持有这些角色则成"角色未承接"，需 M0 实施工程师人工裁决）
]


def _sql_quote(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _emit_iaf_binding_manifest_sql(entries: list[dict]) -> str:
    lines = [
        "DROP TABLE IF EXISTS `iaf_binding_manifest`;",
        "CREATE TABLE `iaf_binding_manifest` (",
        "  `LEGACY_USER_ID` varchar(36),",
        "  `LEGACY_USER_CODE` varchar(36),",
        "  `ACCOUNT` varchar(128),",
        "  `IAF_SUB` varchar(128),",
        "  `PREFERRED_USERNAME` varchar(128),",
        "  `BINDING_STATUS` varchar(32)",
        ") ENGINE=InnoDB;",
    ]
    for row in entries:
        values = [
            _sql_quote(row.get("legacy_user_id")),
            _sql_quote(row.get("legacy_user_code")),
            _sql_quote(row.get("account")),
            _sql_quote(row.get("iaf_sub")),
            _sql_quote(row.get("preferred_username")),
            _sql_quote(row.get("binding_status", "bound")),
        ]
        lines.append("INSERT INTO `iaf_binding_manifest` VALUES (" + ", ".join(values) + ");")
    return "\n".join(lines) + "\n"


def _emit_role_mapping_manifest_sql(entries: list[dict]) -> str:
    lines = [
        "DROP TABLE IF EXISTS `role_mapping_manifest`;",
        "CREATE TABLE `role_mapping_manifest` (",
        "  `LEGACY_ROLE_REF` varchar(128),",
        "  `TARGET_TYPE` varchar(16),",
        "  `TARGET_ROLE_CODE` varchar(64),",
        "  `TARGET_TAG` varchar(64),",
        "  `CONFIDENCE` varchar(32)",
        ") ENGINE=InnoDB;",
    ]
    for row in entries:
        values = [
            _sql_quote(row.get("legacy_role_ref")),
            _sql_quote(row.get("target_type", "role")),
            _sql_quote(row.get("target_role_code")),
            _sql_quote(row.get("target_tag")),
            _sql_quote(row.get("confidence", "confirmed")),
        ]
        lines.append("INSERT INTO `role_mapping_manifest` VALUES (" + ", ".join(values) + ");")
    return "\n".join(lines) + "\n"


def _emit_capability_mapping_manifest_sql(entries: list[dict]) -> str:
    lines = [
        "DROP TABLE IF EXISTS `capability_mapping_manifest`;",
        "CREATE TABLE `capability_mapping_manifest` (",
        "  `LEGACY_PERMISSION_REF` varchar(128),",
        "  `CAPABILITY_ID` varchar(128),",
        "  `SURFACE` varchar(32),",
        "  `CANDIDATE_STATUS` varchar(32),",
        "  `MANIFEST_VERSION` varchar(32)",
        ") ENGINE=InnoDB;",
    ]
    for row in entries:
        values = [
            _sql_quote(row.get("legacy_permission_ref")),
            _sql_quote(row.get("capability_id")),
            _sql_quote(row.get("surface", "webui")),
            _sql_quote(row.get("candidate_status", "pending_review")),
            _sql_quote(row.get("manifest_version", "m0-sd-default-v1")),
        ]
        lines.append("INSERT INTO `capability_mapping_manifest` VALUES (" + ", ".join(values) + ");")
    return "\n".join(lines) + "\n"


def manifest_sql_for_test(iaf_entries, role_entries, capability_entries) -> str:
    """test 调用此函数把 fixture 转回 SQL，附在真实 dump 末尾给 GovernanceMapper 消化。"""
    return (
        _emit_iaf_binding_manifest_sql(iaf_entries)
        + "\n"
        + _emit_role_mapping_manifest_sql(role_entries)
        + "\n"
        + _emit_capability_mapping_manifest_sql(capability_entries)
    )


# ---------------------------------------------------------------------------
# 解析真实 dump — 复用生产 mapper 的 MysqldumpParser，避免自维护 CSV/quote 解析器漂移。
# ---------------------------------------------------------------------------
def _iter_table_rows(table: str) -> list[dict[str, object]]:
    from zw_brain.adapters.legacy.parser import MysqldumpParser

    rows: list[dict[str, object]] = []
    for tbl, row in MysqldumpParser(DUMP).iter_rows():
        if tbl == table:
            rows.append(row)
    return rows


def _registered_skill_ids() -> set[str]:
    out: set[str] = set()
    reg_dir = REPO_ROOT / "zw_brain/capability_registry/registered"
    for path in reg_dir.glob("*.json"):
        try:
            out.add(json.loads(path.read_text(encoding="utf-8")).get("skill_id", ""))
        except Exception:  # noqa: BLE001
            continue
    return {s for s in out if s}


# pub_resource URL 前缀 → capability_id；只保留已注册 Skill。
# 来源参考 scripts/regenerate_bsp_capability_manifest.py:66-；这里扩展几个高频 BSP 资源。
RES_PATH_TO_CAPABILITY: list[tuple[str, str]] = [
    # 顺序敏感：先长前缀匹配，再短前缀兜底。
    # —— 旧 BSP 真实 dump 中前 20 个高频 prefix 直接对齐 zw-brain Skill ——
    ("/dsp/catalog", "catalog.entry.query"),          # 42 资源
    ("/dsp/example", "catalog.browse"),                # 22 示例资源浏览
    ("/dsp/exchange", "delivery.exchange.plan"),       # 16 交换/交付
    ("/dsp/require", "request.list"),                  # 14 需求/申请
    ("/dsp/duty", "ops.shift_handover.submit"),        # 6 值班
    ("/dsp/connect", "delivery.exchange.publish"),     # 6 对接
    ("/dsp/catalogquality", "ops.catalog.quality.query"),  # 6 质量
    ("/dsp/announcement", "workbench.view"),
    ("/manage/perform", "ops.service.invocation.query"),  # 11 性能监控
    ("/manage/report", "ops.service.report.query"),    # 6 报表
    ("/manage/resource", "resource.asset.query"),
    ("/manage/catalog", "catalog.entry.query"),
    ("/manage/zone", "zone.list"),
    ("/manage/objection", "governance.dispute_list"),
    ("/home/audit", "audit.list"),                      # 10 审计
    ("/home/apply", "request.list"),                    # 7 我的申请
    ("/api/resource", "resource.asset.query"),          # 9 资源 API
    ("/portal/catalog", "catalog.browse"),
    ("/portal/zone", "zone.list"),
    ("/portal/credential", "credential.query"),
    ("/portal/request", "request.list"),
    ("/accept", "governance.dispute_view"),
    ("/handling", "governance.dispute_list"),
    # —— 旧 SAMPLE 路径（其它 PR 已对齐）——
    ("/catalog/search", "catalog.entry.query"),
    ("/catalog/entry/create", "catalog.entry.create"),
    ("/catalog/entry/update", "catalog.entry.update"),
    ("/catalog/entry/submit", "catalog.entry.submit_review"),
    ("/catalog/review/execute", "catalog.entry.review"),
    ("/catalog/publish/execute", "catalog.entry.publish"),
    ("/catalog/resource/list", "resource.asset.query"),
    ("/catalog/request/create", "request.create"),
    ("/catalog/request/pending/list", "request.list"),
    ("/catalog/credential/list", "credential.query"),
    ("/bsp/system/audit/list", "audit.list"),
    ("/bsp/evidence/chain", "audit.replay_evidence_chain"),
    ("/bsp/dashboard", "workbench.view"),
]


def build_iaf_binding_entries(users: list[dict[str, object]]) -> list[dict]:
    """M0 首登前为每个 pub_user 生成 synthetic iaf-sub（M0 实施时由客户 IAM 真实 sub 替换）。
    sub 取 sha1(legacy_user_id)[:24]，前缀 'iaf-sd-' 标明 sd-default 测试占位。"""
    out: list[dict] = []
    for row in users:
        legacy_user_id = str(row.get("ID") or "")
        if not legacy_user_id:
            continue
        account = str(row.get("ACCOUNT") or "") or legacy_user_id
        name = str(row.get("NAME") or "") or account
        sub = "iaf-sd-" + hashlib.sha1(legacy_user_id.encode()).hexdigest()[:24]
        out.append(
            {
                "legacy_user_id": legacy_user_id,
                "legacy_user_code": legacy_user_id,
                "account": account,
                "iaf_sub": sub,
                "preferred_username": account or name,
                "binding_status": "bound",
            }
        )
    return out


def build_role_mapping_entries() -> list[dict]:
    out: list[dict] = []
    for legacy_ref, target_type, target_role_code, target_tag, rationale in ROLE_MAPPING:
        out.append(
            {
                "legacy_role_ref": legacy_ref,
                "target_type": target_type,
                "target_role_code": target_role_code,
                "target_tag": target_tag,
                "confidence": "confirmed",
                "rationale": rationale,
            }
        )
    return out


def build_capability_mapping_entries(resources: list[dict[str, object]]) -> list[dict]:
    registered = _registered_skill_ids()
    out: list[dict] = []
    seen: set[str] = set()
    for row in resources:
        res_id = str(row.get("ID") or "")
        path = str(row.get("PATH") or "")
        name = str(row.get("NAME") or "")
        if not res_id or not path:
            continue
        cap: str | None = None
        for prefix, cid in RES_PATH_TO_CAPABILITY:
            if path.startswith(prefix):
                cap = cid if cid in registered else None
                break
        if not cap or res_id in seen:
            continue
        seen.add(res_id)
        out.append(
            {
                "legacy_permission_ref": res_id,
                "capability_id": cap,
                "surface": "webui",
                "candidate_status": "pending_review",
                "manifest_version": "m0-sd-default-v1",
                "legacy_path": path,
                "legacy_name": name,
            }
        )
    return out


def main() -> int:
    if not DUMP.exists():
        print(f"missing real dump: {DUMP}", file=sys.stderr)
        return 1

    users = _iter_table_rows("pub_user")
    resources = _iter_table_rows("pub_resource")
    print(f"parsed {len(users)} pub_user rows, {len(resources)} pub_resource rows", file=sys.stderr)

    iaf = build_iaf_binding_entries(users)
    role = build_role_mapping_entries()
    cap = build_capability_mapping_entries(resources)
    print(f"emit: iaf={len(iaf)} role={len(role)} capability={len(cap)}", file=sys.stderr)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "iaf-binding-manifest.json").write_text(
        json.dumps(
            {
                "manifest_type": "iaf_binding_manifest",
                "tenant_id": "sd-default",
                "manifest_version": "m0-sd-default-v1",
                "description": (
                    "synthetic IAF sub baseline for old/10示例数据/dump-dsp_bsp-202604271139.sql; "
                    "客户 M0 实施时替换为真实 IAM directory sub"
                ),
                "entries": iaf,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "role-mapping-manifest.json").write_text(
        json.dumps(
            {
                "manifest_type": "role_mapping_manifest",
                "tenant_id": "sd-default",
                "manifest_version": "m0-sd-default-v1",
                "description": (
                    "73 legacy ROLE_* → 6 个产品 BUSINESS_ROLE_CODES baseline；"
                    "M0 实施工程师可在现场基于客户实际语义微调，结果回流本 fixture。"
                ),
                "rows": role,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "capability-mapping-manifest.json").write_text(
        json.dumps(
            {
                "manifest_type": "capability_mapping_manifest",
                "tenant_id": "sd-default",
                "manifest_version": "m0-sd-default-v1",
                "description": (
                    "pub_resource.ID → capability_id by URL 前缀匹配；只收录已注册 Skill。"
                    "未命中前缀的资源由 mapper 留 unmapped_permission issue，需现场补充映射规则。"
                ),
                "rows": cap,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote 3 manifests to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
