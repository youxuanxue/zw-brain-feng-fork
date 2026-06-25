from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

import zw_brain.domain.models  # noqa: F401 — 副作用：注册全部 ORM 表到 Base.metadata（alembic env.py / 反射对账依赖）
from zw_brain.shared.db import get_database_url

# ════════════════════════════════════════════════════════════════════════════
# Schema 演进 = alembic forward-migration（D58，反转 D23 二次升级）
# ════════════════════════════════════════════════════════════════════════════
# D23 当年把 alembic 整体删除、冷启动走 drop_all+create_all：任何 schema 漂移都
# DROP 全表重建。这对**生产试用库**是数据丢失风险（一次列名漂移 = 整库清空）。
# D58 反转：用 alembic 向前迁移取代「漂移即 DROP」。
#   - 空库          → run_migrations()（upgrade head）建全部 76 表；
#   - 有 alembic_version → run_migrations()（upgrade head）幂等续迁；
#   - 有数据但无版本表（存量库）→ stamp baseline（零 DDL、保数据）再 upgrade head；
#   - prod 下检测真漂移且无迁移可上 → raise 拒启（绝不 DROP）。
# reset_and_upgrade() 保留但闸在 ZW_BRAIN_ALLOW_SCHEMA_RESET=1 之后（M5 fail-closed）。
#
# REQUIRED_TABLES / REQUIRED_COLUMNS 保留为运行时自检清单（独立于 Base 的反射式校验），
# 用来在 ensure_runtime_schema 里判断「存量库 schema 是否与当前模型一致」从而决定 stamp/迁移分支。

# alembic baseline revision（alembic/versions/*_baseline.py 的 revision id）。
# upgrade=建全部 76 表（== Base.metadata.create_all），downgrade=drop 全部。
BASELINE_REVISION = "77da8251e66d"

REQUIRED_TABLES = {
    "runtime_state",
    "agent_runtime_agent_state",
    "audit_event",
    "capability_call",
    "anchor_outbox",
    "audit_receipt",
    "capability_manifest",
    "catalog_model",
    "catalog_model_field",
    "catalog_entry",
    "catalog_entry_version",
    "catalog_item",
    "resource_asset",
    "resource_channel_binding",
    "resource_schema_mapping",
    "resource_schema_snapshot",
    "metadata_gather_evidence_projection",
    "lineage_relation_projection",
    "quality_evidence_projection",
    "resource_api_test_projection",
    "gateway_runtime_status_projection",
    "datasource_endpoint_projection",
    "service_invocation_metric_projection",
    "legacy_object_mapping",
    "external_object_mapping",
    "adapter_run_record",
    "tenant_projection",
    "org_projection",
    "region_projection",
    "role_projection",
    "actor_projection",
    "actor_org_role_binding",
    "legacy_policy_mapping_candidate",
    "topic_package",
    "topic_package_item",
    "topic_package_visibility",
    "topic_package_review_record",
    "topic_package_evidence",
    "topic_package_metric_projection",
    "application_record",
    "approval_case",
    "approval_step",
    "approval_decision",
    "delivery_task",
    "delivery_receipt",
    "delivery_subscription",
    "delivery_attempt",
    "delivery_execution_evidence",
    "exchange_metric_projection",
    "objection_case",
    "objection_evidence",
    "objection_process",
    "objection_evaluation",
    "capability_package",
    "tenant_capability_policy",
    "approval_flow_schema",
    "approval_flow_node",
    "approval_flow_selection_rule",
    "approval_flow_branch",
    "form_schema",
    "form_section",
    "form_field",
    "form_validator",
    "recommendation_rule",
    "recommendation_rule_clause",
    "requirement_history",
    "requirement_submission",
}

# 这些表是 baseline revision 之后新增的 forward migrations。存量库若尚未被
# alembic 纳管，允许先按 baseline 表集合判断并 stamp，再由 upgrade head 补建。
POST_BASELINE_TABLES = {
    "agent_runtime_agent_state",
    "datasource_endpoint_projection",
}

REQUIRED_COLUMNS = {
    "capability_call": {"call_ref", "tenant_id", "skill_id", "role_code", "status", "input_json", "output_json"},
    "catalog_model": {"model_code", "model_schema_json"},
    "catalog_model_field": {"model_code", "field_code", "field_policy_json"},
    "catalog_entry": {"region_code"},
    "catalog_entry_version": {"catalog_code", "version_no", "snapshot_json"},
    "catalog_item": {"item_code", "catalog_code", "resource_code", "item_kind"},
    "resource_asset": {"owner_org_snapshot_json", "region_code", "access_policy_json", "qos_policy_json"},
    "resource_channel_binding": {"endpoint_ref", "schema_ref"},
    "resource_schema_mapping": {"catalog_item_code", "source_schema_ref", "mapping_rule_json", "confidence_level"},
    "resource_schema_snapshot": {"snapshot_ref", "schema_json", "schema_hash"},
    "metadata_gather_evidence_projection": {"gather_task_ref", "schema_snapshot_ref", "error_summary"},
    "lineage_relation_projection": {"relation_ref", "relation_scope", "relation_rule_json"},
    "quality_evidence_projection": {"quality_ref", "quality_status", "evidence_json"},
    "gateway_runtime_status_projection": {"runtime_profile"},
    "datasource_endpoint_projection": {"connection_ref", "display_name", "data_partition", "connectivity_status"},
    "service_invocation_metric_projection": {"provider_region_code", "consumer_region_code", "bucket_granularity", "provider_error_count", "consumer_error_count", "gateway_error_count", "other_error_count", "apply_count", "p95_latency_ms", "last_error_code", "last_error_at", "failed_count"},
    "legacy_object_mapping": {"mapping_status"},
    "external_object_mapping": {"external_system", "direction", "local_aggregate_type", "external_object_id", "last_receipt_json"},
    "adapter_run_record": {"adapter_slug", "operation", "idempotency_key", "receipt_json", "status"},
    "tenant_projection": {"tenant_id", "tenant_name", "status", "profile_json"},
    "org_projection": {"tenant_id", "org_code", "org_name", "region_code", "profile_json"},
    "actor_projection": {"tenant_id", "external_actor_id", "display_name", "role_codes_json"},
    "actor_org_role_binding": {
        "tenant_id",
        "external_actor_id",
        "org_code",
        "role_code",
        "binding_status",
        "tags_json",
        "valid_from",
        "valid_to",
        "granted_by",
        "batch_no",
        "source_priority",
        "evidence_json",
    },
    "legacy_policy_mapping_candidate": {"legacy_system", "legacy_permission_ref", "capability_id", "candidate_status"},
    "topic_package": {"package_code", "title", "scenario", "status", "display_snapshot_json"},
    "topic_package_item": {"package_code", "item_code", "ref_type", "ref_id"},
    "topic_package_visibility": {"package_code", "visibility_code", "policy_status", "condition_json"},
    "topic_package_review_record": {"package_code", "action_type", "action_result", "to_status"},
    "topic_package_evidence": {"package_code", "evidence_type", "content_json"},
    "topic_package_metric_projection": {"package_code", "metric_key", "metric_value", "metric_json"},
    "approval_step": {"decision_mode", "started_at", "completed_at"},
    "approval_decision": {"decision_reason"},
    "delivery_receipt": {"receipt_no", "acknowledged_at"},
    "delivery_subscription": {"subscription_code", "delivery_code", "resource_code", "schedule_ref_json", "policy_snapshot_json"},
    "delivery_attempt": {"attempt_code", "delivery_code", "attempt_kind", "state", "payload_json"},
    "delivery_execution_evidence": {"evidence_ref", "delivery_code", "attempt_code", "result_status", "sanitized_payload_json"},
    "exchange_metric_projection": {"metric_scope", "delivery_code", "exchange_count", "success_count", "failed_count", "summary_json"},
    "agent_runtime_agent_state": {"tenant_id", "agent_id", "enabled", "allowed_roles_json", "updated_by", "reason"},
}

def _resolve_alembic_paths() -> tuple[Path, Path]:
    """定位 alembic.ini + alembic/ —— 兼容开发态（仓根）与 wheel 安装态（打包进 package）。

    两种部署形态：
      - 开发态：migrate.py 在 <repo>/zw_brain/shared/ → parents[2] = 仓根，alembic.ini/alembic/ 在仓根；
      - 生产 wheel：force-include 把它们打到 zw_brain/_migrations/（与本模块同 package），
        site-packages 里没有仓根 alembic.ini —— 故优先解析 package 内的 _migrations/。
    优先 package 内（生产路径），回落仓根（开发路径），保证两端 run_migrations 都能定位。
    """
    pkg_migrations = Path(__file__).resolve().parents[1] / "_migrations"  # zw_brain/_migrations/
    repo_root = Path(__file__).resolve().parents[2]                       # 仓根
    for base in (pkg_migrations, repo_root):
        ini = base / "alembic.ini"
        script_dir = base / "alembic"
        if ini.is_file() and script_dir.is_dir():
            return ini, script_dir
    # 都不存在 → 回落仓根（让 alembic 报清晰的 FileNotFoundError，而非静默走错路径）。
    return repo_root / "alembic.ini", repo_root / "alembic"


_ALEMBIC_INI, _ALEMBIC_DIR = _resolve_alembic_paths()

_ALLOW_SCHEMA_RESET_ENV = "ZW_BRAIN_ALLOW_SCHEMA_RESET"
_PROD_DEPLOY_MODES = {"prod", "production"}


class SchemaDriftError(RuntimeError):
    """生产模式检测到真实 schema 漂移、且无迁移可向前应用 → 拒启（绝不 DROP）。

    D58 fail-closed：drop_all 是数据丢失风险。生产试用库若出现与当前模型不一致的
    schema，正确做法是写一条向前迁移再 upgrade，而不是清库。在没有可上迁移时直接
    拒绝启动，把问题暴露给运维（要么补迁移、要么显式 ALLOW_SCHEMA_RESET 走重置）。
    """


class SchemaResetForbiddenError(RuntimeError):
    """reset_and_upgrade()（drop_all+create_all）在未显式开 ALLOW_SCHEMA_RESET 时被调 → 拒绝。

    M5 fail-closed 姿态（仿 DevBypassInProductionError）：破坏性重置必须显式承认。
    """


def _is_prod_deploy_mode() -> bool:
    # 复用既有 deploy-mode 信号（ZW_BRAIN_DEPLOY_MODE），不另造平行 prod flag。
    return os.environ.get("ZW_BRAIN_DEPLOY_MODE", "").strip().lower() in _PROD_DEPLOY_MODES


def _schema_reset_allowed() -> bool:
    return os.environ.get(_ALLOW_SCHEMA_RESET_ENV, "").strip() == "1"


def _alembic_config():
    """构造指向本仓 alembic.ini / alembic/ + 真实 DB URL 的 alembic Config（编程式调用）。"""
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    return cfg


def _current_db_revision() -> str | None:
    """读 alembic_version 表里的当前 revision；无版本表 → None。"""
    engine = create_engine(get_database_url(), future=True)
    try:
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            return None
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            return row[0] if row else None
    finally:
        engine.dispose()


def _schema_matches_baseline() -> bool:
    """存量库 schema 是否与 baseline 模型一致（baseline REQUIRED_TABLES/COLUMNS 全满足）。

    一致 → 可安全 stamp baseline（零 DDL）；不一致 → 真漂移，需迁移而非 stamp。
    """
    engine = create_engine(get_database_url(), future=True)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        baseline_required_tables = REQUIRED_TABLES - POST_BASELINE_TABLES
        if not baseline_required_tables.issubset(tables):
            return False
        for table_name, required_columns in REQUIRED_COLUMNS.items():
            if table_name in POST_BASELINE_TABLES:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if not required_columns.issubset(columns):
                return False
        return True
    finally:
        engine.dispose()


def _db_is_empty() -> bool:
    """库里除 alembic_version 外没有任何业务表 → 视作空库。"""
    engine = create_engine(get_database_url(), future=True)
    try:
        tables = set(inspect(engine).get_table_names())
        tables.discard("alembic_version")
        return not tables
    finally:
        engine.dispose()


def run_migrations() -> None:
    """alembic upgrade head（编程式）。建表 / 向前迁移的唯一入口（D58）。"""
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def stamp_baseline_if_legacy() -> bool:
    """存量库（非空 + 无 alembic_version + schema 与模型一致）→ stamp baseline（零 DDL、保数据）。

    返回 True 表示执行了 stamp；False 表示不适用（空库 / 已有版本表 / schema 不一致）。
    """
    from alembic import command

    if _current_db_revision() is not None:
        return False  # 已纳管
    if _db_is_empty():
        return False  # 空库，走 run_migrations 建表，不 stamp
    if not _schema_matches_baseline():
        return False  # 真漂移，不能假装 baseline
    command.stamp(_alembic_config(), BASELINE_REVISION)
    return True


def upgrade() -> None:
    """建表入口（保留旧名兼容历史调用）。空库直接 run_migrations。

    历史上 upgrade() = create_all；现收口到 alembic（upgrade head 对空库等价建全部 76 表）。
    """
    run_migrations()


def reset_and_upgrade() -> None:
    """Drop 全表后重建（破坏性）。仅在 ZW_BRAIN_ALLOW_SCHEMA_RESET=1 时可调，否则 raise（M5）。

    保留供「显式重置」路径（migration_batch.py --reset-db / 开发态 rebuild），绝不在
    ensure_runtime_schema 自动路径里被调（D58：漂移即 DROP 已退役）。
    """
    if not _schema_reset_allowed():
        raise SchemaResetForbiddenError(
            "reset_and_upgrade() drops all tables (data loss). 显式破坏性重置必须设置 "
            f"{_ALLOW_SCHEMA_RESET_ENV}=1 才能调用（M5 fail-closed，D58）。"
            "生产/试用库严禁此路径；正确演进 schema 应写 alembic 向前迁移后 upgrade head。"
        )
    engine = create_engine(get_database_url(), future=True)
    with engine.begin() as conn:
        inspector = inspect(conn)
        # CASCADE 必需：D48 起表间有 17 条 FK 边，PG 严格执行 FK，按反射顺序
        # 裸 DROP 会因被引用而 raise。CASCADE 连带 drop 依赖约束（单 PG 后端，
        # 不再需要兼容 SQLite 的「无 FK、任意顺序可删」假设）。
        for table_name in inspector.get_table_names():
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
    engine.dispose()
    run_migrations()


def ensure_runtime_schema() -> None:
    """冷启动 schema 收敛（D58：forward-migration，绝不 DROP）。

    分支：
      - 有 alembic_version → run_migrations()（幂等 upgrade head，续迁）；
      - 无版本表 + 空库     → run_migrations()（建全部 76 表）；
      - 无版本表 + 有数据 + schema 与模型一致（存量库）→ stamp baseline（零 DDL、保数据）后 upgrade head；
      - 无版本表 + 有数据 + schema 真漂移 → 生产模式 raise SchemaDriftError 拒启（绝不 DROP）；
        非生产模式同样 raise（开发者应显式 ALLOW_SCHEMA_RESET 走 reset，或补迁移），不再静默 DROP。
    """
    if _current_db_revision() is not None:
        run_migrations()
        return

    if _db_is_empty():
        run_migrations()
        return

    # 有数据但无 alembic_version：存量库或真漂移。
    if _schema_matches_baseline():
        stamp_baseline_if_legacy()
        run_migrations()
        return

    # 有数据 + schema 与当前模型不一致 = 真漂移，无迁移可上 → 拒启（绝不 DROP，D58）。
    mode = "production" if _is_prod_deploy_mode() else "non-production"
    raise SchemaDriftError(
        f"DB 非空、无 alembic_version、且 schema 与当前模型不一致（真实漂移，{mode}）。"
        "D58：绝不 drop_all 重建（数据丢失风险）。请补一条 alembic 向前迁移后 upgrade head；"
        f"如确认可丢弃数据，显式设置 {_ALLOW_SCHEMA_RESET_ENV}=1 走 reset_and_upgrade()。"
    )
