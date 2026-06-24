"""国家扩展要素编制任务仓储（D50/C5）。

只读写 ``national_ext_elem_compile_task`` / ``national_basic_elem_catalog`` 两张国家扩展要素
专有表 —— **绝不触碰政务目录主线表**（catalog_entry/catalog_item），双轨硬隔离
（national-ext-elements.feature 场景4）。编制态迁移一律经 ``national_ext_elem_walker``
校验（fail-closed），不在仓储里散落状态判断。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain import national_ext_elem_walker as walker
from zw_brain.domain.models import (
    NationalBasicElemCatalogRecord,
    NationalExtElemCompileTaskRecord,
)
from zw_brain.shared.db import create_session_factory


def _now() -> datetime:
    return datetime.now(UTC)


def task_to_dict(rec: NationalExtElemCompileTaskRecord) -> dict[str, Any]:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "task_code": rec.task_code,
        "title": rec.title,
        "basic_elem_catalog_id": rec.basic_elem_catalog_id,
        "compile_status": rec.compile_status,
        "task_create_organ_code": rec.task_create_organ_code,
        "task_receiver_code": rec.task_receiver_code,
        "current_review_step": rec.current_review_step,
        "payload_json": rec.payload_json or {},
        "created_by": rec.created_by,
    }


class NationalExtElemRepository:
    DEFAULT_TENANT = "sd-default"

    def create_task(self, payload: dict[str, Any], *, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        """新建编制任务（初始 draft）。task_code 租户内幂等（已存在则返回既有）。"""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            existing = session.execute(
                select(NationalExtElemCompileTaskRecord).where(
                    NationalExtElemCompileTaskRecord.tenant_id == tenant_id,
                    NationalExtElemCompileTaskRecord.task_code == payload["task_code"],
                )
            ).scalar_one_or_none()
            if existing is not None:
                return task_to_dict(existing)
            rec = NationalExtElemCompileTaskRecord(
                tenant_id=tenant_id,
                task_code=payload["task_code"],
                title=payload.get("title") or payload["task_code"],
                basic_elem_catalog_id=payload.get("basic_elem_catalog_id"),
                compile_status=walker.DRAFT,
                task_create_organ_code=payload.get("task_create_organ_code"),
                task_receiver_code=payload.get("task_receiver_code"),
                current_review_step=None,
                payload_json=payload.get("payload_json") or {},
                created_by=payload.get("created_by"),
            )
            session.add(rec)
            session.commit()
            return task_to_dict(session.get(NationalExtElemCompileTaskRecord, rec.id))

    def get_task(self, task_code: str, *, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any] | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(NationalExtElemCompileTaskRecord).where(
                    NationalExtElemCompileTaskRecord.tenant_id == tenant_id,
                    NationalExtElemCompileTaskRecord.task_code == task_code,
                )
            ).scalar_one_or_none()
            return task_to_dict(rec) if rec is not None else None

    def list_tasks(
        self, *, tenant_id: str = DEFAULT_TENANT, compile_status: str | None = None
    ) -> list[dict[str, Any]]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            stmt = select(NationalExtElemCompileTaskRecord).where(
                NationalExtElemCompileTaskRecord.tenant_id == tenant_id
            )
            if compile_status:
                stmt = stmt.where(NationalExtElemCompileTaskRecord.compile_status == compile_status)
            rows = session.execute(stmt.order_by(NationalExtElemCompileTaskRecord.task_code)).scalars()
            return [task_to_dict(r) for r in rows]

    def set_status(
        self,
        task_code: str,
        to_status: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
        current_review_step: int | None = None,
    ) -> dict[str, Any]:
        """迁移编制态（经 walker 校验，非法 → raise）。审核态可同步 current_review_step。"""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(NationalExtElemCompileTaskRecord).where(
                    NationalExtElemCompileTaskRecord.tenant_id == tenant_id,
                    NationalExtElemCompileTaskRecord.task_code == task_code,
                )
            ).scalar_one_or_none()
            if rec is None:
                raise KeyError(f"national ext-elem task not found: {task_code}")
            walker.validate_transition(rec.compile_status, to_status)
            rec.compile_status = to_status
            rec.current_review_step = current_review_step
            rec.updated_at = _now()
            session.commit()
            return task_to_dict(session.get(NationalExtElemCompileTaskRecord, rec.id))

    def review_decision(
        self, task_code: str, *, approve: bool, tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, Any]:
        """业务部门/主管部门审核决策 → 经 walker 推下一态（approve 串行进，reject 回退）。"""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(NationalExtElemCompileTaskRecord).where(
                    NationalExtElemCompileTaskRecord.tenant_id == tenant_id,
                    NationalExtElemCompileTaskRecord.task_code == task_code,
                )
            ).scalar_one_or_none()
            if rec is None:
                raise KeyError(f"national ext-elem task not found: {task_code}")
            nxt = walker.next_review_status(rec.compile_status, approve=approve)
            rec.compile_status = nxt
            # 进入主管部门审核（含变更链）→ 第 2 步；待同步/发布/回退/草稿清空步号。
            rec.current_review_step = (
                2
                if nxt in (walker.PENDING_SUPERVISOR_REVIEW, walker.PENDING_SUPERVISOR_REVIEW_REVISION)
                else None
            )
            rec.updated_at = _now()
            session.commit()
            return task_to_dict(session.get(NationalExtElemCompileTaskRecord, rec.id))

    def upsert_basic_elem_catalog(
        self, payload: dict[str, Any], *, tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, Any]:
        """登记一条基本要素目录（国家下发后导入）。按 (tenant, cata_id, version) 幂等。"""
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            rec = session.execute(
                select(NationalBasicElemCatalogRecord).where(
                    NationalBasicElemCatalogRecord.tenant_id == tenant_id,
                    NationalBasicElemCatalogRecord.cata_id == payload["cata_id"],
                    NationalBasicElemCatalogRecord.version == payload.get("version", 1),
                )
            ).scalar_one_or_none()
            if rec is None:
                rec = NationalBasicElemCatalogRecord(
                    tenant_id=tenant_id,
                    cata_id=payload["cata_id"],
                    version=payload.get("version", 1),
                    cata_title=payload.get("cata_title") or payload["cata_id"],
                    category_code=payload.get("category_code"),
                    domain_id=payload.get("domain_id"),
                    level=payload.get("level"),
                    imported_by_org_code=payload.get("imported_by_org_code"),
                )
                session.add(rec)
                session.commit()
            return {"id": rec.id, "cata_id": rec.cata_id, "version": rec.version, "cata_title": rec.cata_title}
