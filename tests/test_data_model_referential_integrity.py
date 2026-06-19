"""数据模型参照完整性 — FK + CASCADE 落地守卫（M1/M2/M3）.

配套设计：docs/decisions/data-model-referential-integrity-design.md
配套守卫脚本：scripts/check_orphan_rows.py

产品保证：「zw-brain 永不留孤儿行——删父级联或拒绝，由系统机制强制」。
本测试核实：
  - A 类 12 条父-PK 边 + B 类 5 条 topic_package 复合边均已建 FK + ON DELETE CASCADE；
  - 干净库 FK 强制下，删父级联删子（孤儿=0）；
  - 引用不存在父行的子写入被 DB 拒绝；
  - check_orphan_rows.py 对全部父子边（含 FK 覆盖不到的 C 类降级边）扫孤儿。

PG-only：库由根 conftest 的 autouse fixture 提供（每测一个 CREATE DATABASE …
TEMPLATE 克隆的、已 alembic upgrade head 的空 PG 库）。FK 元数据走方言无关的
SQLAlchemy inspect()；孤儿守卫对同一个克隆库跑 check_orphan_rows.py --db-url。
PostgreSQL 真实强制 FK——A/B 类有 FK+CASCADE 的边构造不出孤儿，只能在无 FK 的
C 类边造孤儿，这正是 M3 守卫的兜底职责（D48）。库供给与隔离全由 conftest 接管。
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from zw_brain.domain.models import (
    ApprovalCaseRecord,
    ApprovalStepRecord,
    Base,
    TopicPackageItemRecord,
    TopicPackageRecord,
)
from zw_brain.shared import db as db_module

# A 类 12 条边：子表 → (引用列, 父表, 父列)。与设计 §1.2 A 类表一致。
A_CLASS_EDGES = {
    "approval_step": ("approval_case_id", "approval_case", "id"),
    "approval_decision": ("step_id", "approval_step", "id"),
    "objection_evidence": ("objection_id", "objection_case", "id"),
    "objection_process": ("objection_id", "objection_case", "id"),
    "objection_evaluation": ("objection_id", "objection_case", "id"),
    "form_section": ("form_schema_id", "form_schema", "id"),
    "form_field": ("form_schema_id", "form_schema", "id"),
    "form_validator": ("form_schema_id", "form_schema", "id"),
    "approval_flow_node": ("schema_id", "approval_flow_schema", "id"),
    "approval_flow_selection_rule": ("schema_id", "approval_flow_schema", "id"),
    "approval_flow_branch": ("schema_id", "approval_flow_schema", "id"),
    "recommendation_rule_clause": ("rule_id", "recommendation_rule", "id"),
}

# B 类 5 条 topic_package 复合边（tenant_id, package_code）→ topic_package。
B_CLASS_TABLES = (
    "topic_package_item",
    "topic_package_visibility",
    "topic_package_review_record",
    "topic_package_evidence",
    "topic_package_metric_projection",
)


def _fk_targets(table_name: str) -> list[tuple[str, str, str, str]]:
    """(parent_table, child_col, parent_col, on_delete) via dialect-agnostic inspect.

    SQLAlchemy ``get_foreign_keys`` returns, per FK,
    ``{'constrained_columns','referred_table','referred_columns','options':{'ondelete':..}}``.
    Expand each (possibly composite) FK into one tuple per (child_col, parent_col)
    pair so callers can match on a single column — one tuple per FK column.
    """
    engine = db_module.create_session_factory().kw["bind"]
    out: list[tuple[str, str, str, str]] = []
    for fk in inspect(engine).get_foreign_keys(table_name):
        ondelete = (fk.get("options") or {}).get("ondelete")
        parent = fk["referred_table"]
        for child_col, parent_col in zip(
            fk["constrained_columns"], fk["referred_columns"], strict=False
        ):
            out.append((parent, child_col, parent_col, ondelete))
    return out


def test_a_class_edges_have_fk_cascade() -> None:
    for child, (col, parent, parent_col) in A_CLASS_EDGES.items():
        targets = _fk_targets(child)
        match = [t for t in targets if t[0] == parent and t[1] == col]
        assert match, f"{child}.{col} 应有 FK → {parent}.{parent_col}，实测 {targets}"
        assert match[0][2] == parent_col, f"{child}.{col} FK 目标应是 {parent}.{parent_col}"
        assert match[0][3] == "CASCADE", f"{child}.{col} FK 应 ON DELETE CASCADE，实测 {match[0][3]}"


def test_b_class_topic_package_composite_fk_cascade() -> None:
    for child in B_CLASS_TABLES:
        targets = _fk_targets(child)
        tenant = [t for t in targets if t[0] == "topic_package" and t[1] == "tenant_id"]
        pkg = [t for t in targets if t[0] == "topic_package" and t[1] == "package_code"]
        assert tenant and pkg, f"{child} 应有复合 FK → topic_package(tenant_id,package_code)，实测 {targets}"
        assert tenant[0][3] == "CASCADE" and pkg[0][3] == "CASCADE", f"{child} 复合 FK 应 CASCADE"


def test_fk_rejects_ghost_parent() -> None:
    """插入引用不存在父行的子记录 → DB 拒绝（参照完整性 DB 强制）。"""
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        s.add(ApprovalStepRecord(
            approval_case_id="ghost-case",
            step_no=1,
            step_name="x",
            status="pending",
            approver_scope_json={},
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_delete_parent_cascades_children_a_class() -> None:
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        case = ApprovalCaseRecord(
            tenant_id="sd-default",
            application_code="APP-1",
            current_status="in_review",
            decision_payload_json={},
        )
        s.add(case)
        s.flush()
        s.add(ApprovalStepRecord(
            approval_case_id=case.id,
            step_no=1,
            step_name="step",
            status="pending",
            approver_scope_json={},
        ))
        s.commit()
        case_id = case.id

    with SessionLocal() as s:
        s.delete(s.get(ApprovalCaseRecord, case_id))
        s.commit()

    with SessionLocal() as s:
        from sqlalchemy import select
        orphans = list(
            s.execute(
                select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == case_id)
            ).scalars()
        )
        assert orphans == [], f"删父后应无孤儿 approval_step，实得 {len(orphans)}"


def test_delete_parent_cascades_children_b_class() -> None:
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        pkg = TopicPackageRecord(
            tenant_id="sd-default",
            package_code="PKG-1",
            title="t",
            owner_org_snapshot_json={},
            display_snapshot_json={},
            metric_snapshot_json={},
        )
        s.add(pkg)
        s.flush()
        s.add(TopicPackageItemRecord(
            tenant_id="sd-default",
            package_code="PKG-1",
            item_code="IT-1",
            ref_type="catalog_entry",
            ref_id="cat-1",
            title="item",
            summary_json={},
        ))
        s.commit()

    with SessionLocal() as s:
        s.delete(
            s.query(TopicPackageRecord).filter_by(tenant_id="sd-default", package_code="PKG-1").one()
        )
        s.commit()

    with SessionLocal() as s:
        from sqlalchemy import select
        orphans = list(
            s.execute(
                select(TopicPackageItemRecord).where(TopicPackageItemRecord.package_code == "PKG-1")
            ).scalars()
        )
        assert orphans == [], f"删包后应无孤儿 topic_package_item，实得 {len(orphans)}"


def test_metadata_fk_floor() -> None:
    """FK 回潮断言：metadata FK 列数 ≥ 已落地边数（A 类 12 + B 类 5×2 复合 = 22）。"""
    fk_cols = [fk for t in Base.metadata.tables.values() for fk in t.foreign_keys]
    assert len(fk_cols) >= 22, (
        f"FK 列数退化：实测 {len(fk_cols)}，期望 ≥22（A 类 12 + B 类复合 10）。"
        "FK 被悄摘 → 参照完整性回潮，见设计 §六.2。"
    )


# --- M3 孤儿守卫（check_orphan_rows.py）行为核实 -----------------------------

def _run_orphan_guard() -> int:
    """对当前测试克隆库（get_database_url）跑 check_orphan_rows.py --db-url，返回退出码。

    传 --db-url 让守卫体检*这一个* PG 克隆库（M5 体检模式，只读不动）——即测试刚
    写过孤儿的同一个隔离库，而非守卫默认自建的另一个干净一次性库。
    """
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "check_orphan_rows.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--db-url", db_module.get_database_url()],
        capture_output=True,
        text=True,
    )
    return proc.returncode


def test_orphan_guard_clean_seed_passes() -> None:
    """干净 seed 库（标准 initialize 后）孤儿守卫应 PASS。"""
    from zw_brain.shared.database_store import DatabaseStore

    DatabaseStore().initialize()
    assert _run_orphan_guard() == 0, "干净 seed 库孤儿守卫应 PASS（孤儿=0）"


def test_orphan_guard_detects_c_class_orphan() -> None:
    """C 类边（无 FK）注入孤儿子行 → 孤儿守卫 FAIL（M3 是 C 类唯一兜底）。

    delivery_receipt.delivery_code 引用一个不存在的 delivery_task（C 类边无 FK，
    所以 DB 不拦，但 M3 守卫必须查出）。
    """
    from zw_brain.domain.models import DeliveryReceiptRecord
    from zw_brain.shared import db as db_module

    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        s.add(DeliveryReceiptRecord(
            delivery_code="GHOST-DLV-NO-PARENT",
            receipt_type="exchange",
            receipt_status="issued",
            payload_json={},
        ))
        s.commit()  # C 类无 FK，DB 不拦（证明降级现实）

    assert _run_orphan_guard() == 1, "C 类孤儿子行应被 M3 守卫查出 FAIL"


def test_orphan_guard_detects_dangling_catalog_ref() -> None:
    """topic_package_item 引用未录入 catalog_entry 的目录 → 可达性守卫 FAIL（§六.3）。"""
    from zw_brain.domain.models import TopicPackageItemRecord, TopicPackageRecord
    from zw_brain.shared import db as db_module

    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        s.add(TopicPackageRecord(
            tenant_id="sd-default",
            package_code="PKG-DANGLE",
            title="t",
            owner_org_snapshot_json={},
            display_snapshot_json={},
            metric_snapshot_json={},
        ))
        s.flush()
        s.add(TopicPackageItemRecord(
            tenant_id="sd-default",
            package_code="PKG-DANGLE",
            item_code="IT-DANGLE",
            ref_type="catalog_entry",
            ref_id="catalog-not-in-main-table",
            title="x",
            summary_json={},
        ))
        s.commit()

    assert _run_orphan_guard() == 1, "悬挂 catalog_entry 引用应被守卫 FAIL"


# --- M4 缺陷 4 ref 完整性·悬挂引用诚实信号（只读派生，不写库） -----------------

def test_effective_ref_status_dangling_signal() -> None:
    """catalog_entry 引用未录入主表 → effective_ref_status=dangling（纯函数）。"""
    from zw_brain.domain.serializers.topic_package import (
        DANGLING_REF_STATUS,
        effective_ref_status,
    )

    present = {"cat-present"}
    # 命中 → 原样
    assert effective_ref_status("catalog_entry", "cat-present", "active", present_catalog_codes=present) == "active"
    # 未命中 → dangling 诚实信号
    assert effective_ref_status("catalog_entry", "cat-missing", "active", present_catalog_codes=present) == DANGLING_REF_STATUS
    # 非 catalog_entry 多态 ref → 不在本守卫，原样
    assert effective_ref_status("resource", "res-x", "active", present_catalog_codes=present) == "active"
    # 无完整性上下文（None）→ 不臆断，原样
    assert effective_ref_status("catalog_entry", "cat-missing", "active", present_catalog_codes=None) == "active"


def test_topic_item_to_dict_surfaces_dangling() -> None:
    """topic_item_to_dict 带 present_catalog_codes 时悬挂 item 降级 + ref_resolvable=False。"""
    from zw_brain.domain.models import TopicPackageItemRecord
    from zw_brain.domain.serializers.topic_package import topic_item_to_dict

    rec = TopicPackageItemRecord(
        tenant_id="sd-default", package_code="P", item_code="I",
        ref_type="catalog_entry", ref_id="ghost-cat", ref_status="active",
        title="t", summary_json={},
    )
    out = topic_item_to_dict(rec, present_catalog_codes={"other"})
    assert out["ref_status"] == "dangling"
    assert out["ref_resolvable"] is False
    # 未提供上下文 → ref_resolvable=None（诚实未校验）
    out2 = topic_item_to_dict(rec)
    assert out2["ref_status"] == "active"
    assert out2["ref_resolvable"] is None


# --- M5 legacy executor 延迟写守门（父缺位不造孤儿，幂等无写-后-删） ----------

def test_pipelines_executor_skips_when_parent_absent() -> None:
    """_map_exchange_executor：父 DeliveryTask 缺位 → 跳过写 attempt + warn 审计，不造孤儿。"""
    from pathlib import Path

    from zw_brain.adapters.legacy._common import ImportStats
    from zw_brain.adapters.legacy.mappers.pipelines import PipelinesMapper
    from zw_brain.domain.models import DeliveryAttemptRecord, DeliveryTaskRecord
    from zw_brain.shared import db as db_module

    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        s.add(DeliveryTaskRecord(tenant_id="sd-default", delivery_code="SUB-OK", application_code="A", state="active", channel="exchange", payload_json={}))
        s.commit()

    mapper = PipelinesMapper(tenant_id="sd-default")
    stats = ImportStats(schema="dsp_pipelines", dump_path=Path("dsp_pipelines"))
    # 父存在 → 建 attempt
    mapper._map_exchange_executor({"executor_id": "EX-OK", "obj_id": "SUB-OK", "obj_type": 1}, "dsp", stats)
    # 父缺位 → 跳过（不造孤儿）
    mapper._map_exchange_executor({"executor_id": "EX-ORPHAN", "obj_id": "SUB-MISSING", "obj_type": 1}, "dsp", stats)

    with SessionLocal() as s:
        from sqlalchemy import select
        codes = {r.attempt_code for r in s.execute(select(DeliveryAttemptRecord)).scalars()}
    assert codes == {"EX-OK"}, f"父缺位的 executor 不应建 attempt，实得 {codes}"
    assert stats.skipped.get("exchange_executor.skipped_orphan") == 1
    assert any(i["type"] == "orphan_skip_missing_parent" for i in stats.issues)
