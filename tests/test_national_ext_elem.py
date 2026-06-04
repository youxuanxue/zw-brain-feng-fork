"""国家扩展要素编制状态机 + 仓储 + 双轨独立性（D50/C5）.

权威：docs/decisions/national-platform-access-D50.md §三；
SPEC：.testing/waves/wave-3-protocol-tenant-national/features/national-ext-elements.feature。
核实：
  - 编制生命周期推进（草稿→业务部门→主管部门→已发布）+ 历史目录处理（变更/撤销）；
  - 2 级审核复用 approval_flow_walker 走查（业务部门→主管部门有序）；
  - **硬约束**：编制任务与政务目录主线（catalog_entry/catalog_item）完全独立，
    编制写入绝不落政务目录表（场景4 负向）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import text

from zw_brain.domain import national_ext_elem_walker as walker
from zw_brain.domain.repositories.national_ext_elem import NationalExtElemRepository
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "national_ext_elem.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


# ---- 走查器：状态机 + 2 级审核复用 -----------------------------------------


def test_review_steps_reuse_approval_flow_walker() -> None:
    """复用 approval_flow_walker 走查 → 业务部门→主管部门 有序 2 步。"""
    steps = walker.review_step_specs()
    assert [s["step_name"] for s in steps] == ["业务部门审核", "主管部门审核"]
    assert [s["step_no"] for s in steps] == [1, 2]


def test_compile_happy_path_transitions() -> None:
    walker.validate_transition(walker.DRAFT, walker.PENDING_BUSINESS_REVIEW)
    assert walker.next_review_status(walker.PENDING_BUSINESS_REVIEW, approve=True) == walker.PENDING_SUPERVISOR_REVIEW
    assert walker.next_review_status(walker.PENDING_SUPERVISOR_REVIEW, approve=True) == walker.PUBLISHED


def test_review_reject_rolls_back() -> None:
    assert walker.next_review_status(walker.PENDING_BUSINESS_REVIEW, approve=False) == walker.DRAFT
    assert walker.next_review_status(walker.PENDING_SUPERVISOR_REVIEW, approve=False) == walker.PENDING_BUSINESS_REVIEW


def test_history_revision_and_revoke_chains() -> None:
    # 历史目录处理：变更链
    walker.validate_transition(walker.PUBLISHED, walker.REVISION_DRAFT)
    assert walker.submit_target(walker.REVISION_DRAFT) == walker.PENDING_BUSINESS_REVIEW_REVISION
    assert walker.next_review_status(walker.PENDING_SUPERVISOR_REVIEW_REVISION, approve=True) == walker.PUBLISHED
    # 撤销链
    walker.validate_transition(walker.PUBLISHED, walker.PENDING_REVOKE_REVIEW)
    assert walker.next_review_status(walker.PENDING_REVOKE_REVIEW, approve=True) == walker.REVOKED


def test_illegal_transition_rejected() -> None:
    with pytest.raises(walker.NationalExtElemTransitionError):
        walker.validate_transition(walker.DRAFT, walker.PUBLISHED)  # 不能跳过审核
    with pytest.raises(walker.NationalExtElemTransitionError):
        walker.next_review_status(walker.DRAFT, approve=True)  # draft 非可审核态


# ---- 仓储：DB 生命周期 + 父子 FK -------------------------------------------


def test_repo_full_lifecycle_to_published(temp_db: Path) -> None:
    repo = NationalExtElemRepository()
    repo.create_task({"task_code": "C_NAT_001", "title": "国家扩展要素A"}, tenant_id=TENANT)
    assert repo.get_task("C_NAT_001", tenant_id=TENANT)["compile_status"] == walker.DRAFT

    repo.set_status("C_NAT_001", walker.PENDING_BUSINESS_REVIEW, tenant_id=TENANT, current_review_step=1)
    t = repo.review_decision("C_NAT_001", approve=True, tenant_id=TENANT)
    assert t["compile_status"] == walker.PENDING_SUPERVISOR_REVIEW
    assert t["current_review_step"] == 2
    t = repo.review_decision("C_NAT_001", approve=True, tenant_id=TENANT)
    assert t["compile_status"] == walker.PUBLISHED
    assert t["current_review_step"] is None


def test_repo_rejects_illegal_status(temp_db: Path) -> None:
    repo = NationalExtElemRepository()
    repo.create_task({"task_code": "C_NAT_002", "title": "B"}, tenant_id=TENANT)
    with pytest.raises(walker.NationalExtElemTransitionError):
        repo.set_status("C_NAT_002", walker.PUBLISHED, tenant_id=TENANT)


def test_basic_elem_fk_cascade(temp_db: Path) -> None:
    """删基本要素目录 → 级联删其编制任务（FK ON DELETE CASCADE）。"""
    repo = NationalExtElemRepository()
    basic = repo.upsert_basic_elem_catalog({"cata_id": "BASE-1", "cata_title": "基本要素1"}, tenant_id=TENANT)
    repo.create_task(
        {"task_code": "C_NAT_003", "title": "C", "basic_elem_catalog_id": basic["id"]},
        tenant_id=TENANT,
    )
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM national_basic_elem_catalog WHERE id = :i"), {"i": basic["id"]})
        s.commit()
        remaining = s.execute(
            text("SELECT COUNT(*) FROM national_ext_elem_compile_task WHERE basic_elem_catalog_id = :i"),
            {"i": basic["id"]},
        ).scalar()
        assert remaining == 0


# ---- 场景4 负向：双轨硬隔离，绝不写政务目录主线 ----------------------------


def test_compile_never_writes_data_catalog(temp_db: Path) -> None:
    """编制任务推进全程不在政务目录主线（catalog_entry/catalog_item）落任何行。"""
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        before_entry = s.execute(text("SELECT COUNT(*) FROM catalog_entry")).scalar()
        before_item = s.execute(text("SELECT COUNT(*) FROM catalog_item")).scalar()

    repo = NationalExtElemRepository()
    repo.create_task({"task_code": "C_NAT_004", "title": "D"}, tenant_id=TENANT)
    repo.set_status("C_NAT_004", walker.PENDING_BUSINESS_REVIEW, tenant_id=TENANT, current_review_step=1)
    repo.review_decision("C_NAT_004", approve=True, tenant_id=TENANT)
    repo.review_decision("C_NAT_004", approve=True, tenant_id=TENANT)  # → published

    with SessionLocal() as s:
        after_entry = s.execute(text("SELECT COUNT(*) FROM catalog_entry")).scalar()
        after_item = s.execute(text("SELECT COUNT(*) FROM catalog_item")).scalar()
        # 编制任务确实落了它自己的表
        nat = s.execute(text("SELECT COUNT(*) FROM national_ext_elem_compile_task")).scalar()
    assert after_entry == before_entry, "编制不得写入 catalog_entry 政务目录主线"
    assert after_item == before_item, "编制不得写入 catalog_item 政务目录主线"
    assert nat == 1


def test_table_isolation_distinct_from_catalog() -> None:
    """两套表硬隔离：编制任务/基本要素表名与政务目录主线表名不重叠。"""
    from zw_brain.domain.models import (
        NationalBasicElemCatalogRecord,
        NationalExtElemCompileTaskRecord,
    )

    national_tables = {
        NationalExtElemCompileTaskRecord.__tablename__,
        NationalBasicElemCatalogRecord.__tablename__,
    }
    assert national_tables.isdisjoint({"catalog_entry", "catalog_item", "catalog_entry_version"})
