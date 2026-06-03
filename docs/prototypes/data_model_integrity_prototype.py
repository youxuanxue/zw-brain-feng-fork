"""原型（设计层，非生产）— 数据模型参照完整性 PoC（D21 可运行原型 + 机械反向防御）。

配套设计文档：docs/decisions/data-model-referential-integrity-design.md

本脚本**不导入生产 Base / 生产 models**，而是用一套独立的、缩比的 SQLAlchemy
metadata 重演两条候选路径，证明设计成立、并暴露真实约束：

  缺陷 1【FK + ON DELETE】
    - case A：父子用「父 PK」串联（approval_case.id ← approval_step.approval_case_id）
      → 可建 SQL FK + ON DELETE CASCADE，删父级联删子，孤儿=0。
    - case B：父子用「业务码」串联（delivery_task.delivery_code ← delivery_receipt.delivery_code）
      生产现状 delivery_code **无 UNIQUE**，证明此时 SQL FK 直接建不出来；
      要么先补 UNIQUE 才能 FK，要么走应用层删除编排守卫。

  缺陷 4【多态 ref 收录 + 完整性】
    - topic_package_item.ref_id 是多态引用（ref_type ∈ {catalog_entry, resource, bs_resource...}），
      多态列**无法单建 SQL FK**；证明「把被引目录补录进 catalog_entry 主表（可检索 + 可详情）
      + 应用层 ref 解析守卫」是可行替代，并演示删父不级联→需编排兜底。

运行（worktree 无 .venv，用主仓 venv）：
    /path/to/zw-brain/.venv/bin/python docs/prototypes/data_model_integrity_prototype.py
退出码 0 = 全部断言通过。
"""

from __future__ import annotations

import sys

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class ProtoBase(DeclarativeBase):
    """独立原型 Base，与生产 zw_brain.shared.db.Base 完全隔离。"""


# --- case A: 父 PK 串联，可建 FK + CASCADE ----------------------------------
class ApprovalCaseProto(ProtoBase):
    __tablename__ = "p_approval_case"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    current_status: Mapped[str] = mapped_column(String(32))


class ApprovalStepProto(ProtoBase):
    __tablename__ = "p_approval_step"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 关键：FK 指向父 PK + ON DELETE CASCADE
    approval_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("p_approval_case.id", ondelete="CASCADE"),
        index=True,
    )
    step_no: Mapped[int] = mapped_column(Integer, default=1)


# --- case B: 业务码串联，生产 delivery_code 无 UNIQUE -------------------------
class DeliveryTaskNoUnique(ProtoBase):
    """复刻生产现状：delivery_code 只 index，无 UNIQUE。"""

    __tablename__ = "p_delivery_task_nouniq"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_code: Mapped[str] = mapped_column(String(64), index=True)


class DeliveryTaskUnique(ProtoBase):
    """整改候选：给 delivery_code 补 UNIQUE，FK 才有合法目标。"""

    __tablename__ = "p_delivery_task_uniq"
    __table_args__ = (UniqueConstraint("delivery_code", name="uq_p_delivery_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_code: Mapped[str] = mapped_column(String(64), index=True)


# --- case 4: 多态 ref + catalog_entry 收录 ----------------------------------
class CatalogEntryProto(ProtoBase):
    __tablename__ = "p_catalog_entry"
    catalog_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))


class TopicPackageItemProto(ProtoBase):
    __tablename__ = "p_topic_package_item"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    ref_type: Mapped[str] = mapped_column(String(64), index=True)
    ref_id: Mapped[str] = mapped_column(String(128), index=True)


def _engine():
    eng = create_engine("sqlite://", future=True)

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")  # 与生产 shared/db.py:46 同一开关
        cur.close()

    return eng


def case_a_fk_cascade() -> None:
    """父 PK 串联 → FK + ON DELETE CASCADE：删父，子自动消失，无孤儿。"""
    eng = _engine()
    ProtoBase.metadata.create_all(
        eng, tables=[ApprovalCaseProto.__table__, ApprovalStepProto.__table__]
    )
    with Session(eng) as s:
        s.add(ApprovalCaseProto(id="case-1", current_status="in_review"))
        s.add(ApprovalStepProto(id="step-1", approval_case_id="case-1", step_no=1))
        s.add(ApprovalStepProto(id="step-2", approval_case_id="case-1", step_no=2))
        s.commit()

        # 1) 插入期参照完整性：引用不存在的父行被拒
        s.add(ApprovalStepProto(id="step-x", approval_case_id="ghost-case", step_no=9))
        rejected = False
        try:
            s.commit()
        except IntegrityError:
            rejected = True
            s.rollback()
        assert rejected, "FK 应拒绝引用不存在父行的插入"

        # 2) 删父 → 子级联删除，孤儿=0
        s.delete(s.get(ApprovalCaseProto, "case-1"))
        s.commit()
        orphans = s.execute(select(ApprovalStepProto)).scalars().all()
        assert orphans == [], f"CASCADE 后应无孤儿子行，实得 {len(orphans)}"
    print(
        "  [case A] 父PK串联 FK + ON DELETE CASCADE：插入守卫 OK，删父级联 OK，孤儿=0"
    )


def case_b_business_code_needs_unique() -> None:
    """业务码串联：FK 目标必须 UNIQUE。生产 delivery_code 无 UNIQUE → 建不出 FK。"""
    eng = _engine()
    ProtoBase.metadata.create_all(
        eng, tables=[DeliveryTaskNoUnique.__table__, DeliveryTaskUnique.__table__]
    )

    # 现状：delivery_code 无 UNIQUE，SQLite 在首次写入时报 foreign key mismatch
    blocked = False
    try:
        with eng.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.exec_driver_sql(
                "CREATE TABLE p_delivery_receipt_bad ("
                " id TEXT PRIMARY KEY,"
                " delivery_code TEXT,"
                " FOREIGN KEY(delivery_code) REFERENCES p_delivery_task_nouniq(delivery_code)"
                ")"
            )
            conn.exec_driver_sql(
                "INSERT INTO p_delivery_task_nouniq(id, delivery_code) VALUES ('t1','DLV-1')"
            )
            conn.exec_driver_sql(
                "INSERT INTO p_delivery_receipt_bad(id, delivery_code) VALUES ('rcpt1','DLV-1')"
            )
    except OperationalError as exc:  # "foreign key mismatch" — 目标列非 unique
        blocked = True
        assert "foreign key mismatch" in str(exc).lower()
    assert blocked, "delivery_code 无 UNIQUE 时，FK 应建不成（foreign key mismatch）"

    # 整改候选：补 UNIQUE 后 FK 合法
    with eng.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql(
            "CREATE TABLE p_delivery_receipt_ok ("
            " id TEXT PRIMARY KEY,"
            " delivery_code TEXT,"
            " FOREIGN KEY(delivery_code) REFERENCES p_delivery_task_uniq(delivery_code) ON DELETE CASCADE"
            ")"
        )
        conn.exec_driver_sql(
            "INSERT INTO p_delivery_task_uniq(id, delivery_code) VALUES ('t2','DLV-2')"
        )
        conn.exec_driver_sql(
            "INSERT INTO p_delivery_receipt_ok(id, delivery_code) VALUES ('rcpt2','DLV-2')"
        )
    print(
        "  [case B] 业务码串联：delivery_code 无 UNIQUE → FK 建不成（foreign key mismatch），"
        "补 UNIQUE 后 FK+CASCADE 合法"
    )


def case4_polymorphic_ref_and_catalog_enrollment() -> None:
    """多态 ref 无法单建 FK；演示 catalog_entry 收录 + 应用层 ref 解析守卫。"""
    eng = _engine()
    ProtoBase.metadata.create_all(
        eng, tables=[CatalogEntryProto.__table__, TopicPackageItemProto.__table__]
    )
    with Session(eng) as s:
        # 收录：被 F9 专题包引用的目录补录进 catalog_entry 主表 → 可检索 + 可详情
        s.add(CatalogEntryProto(catalog_code="medical-aid", title="医疗救助目录"))
        s.add(
            TopicPackageItemProto(
                id="i1", package_code="P-1", ref_type="catalog_entry", ref_id="medical-aid"
            )
        )
        # 一个尚未收录的多态引用（resource 类）— 合法存在，但需应用层解析
        s.add(
            TopicPackageItemProto(
                id="i2", package_code="P-1", ref_type="resource", ref_id="res-77"
            )
        )
        # 一个悬挂引用（catalog_entry 主表查无此目录）
        s.add(
            TopicPackageItemProto(
                id="i3", package_code="P-1", ref_type="catalog_entry", ref_id="ghost-catalog"
            )
        )
        s.commit()

        # 收录后：catalog_entry 命中 → 详情页/检索可达
        hit = s.get(CatalogEntryProto, "medical-aid")
        assert hit is not None, "收录后目录应可在 catalog_entry 主表命中"

        # 应用层 ref 完整性守卫：对 ref_type=catalog_entry 的 item，校验 catalog_entry 存在
        def dangling_catalog_refs() -> list[str]:
            rows = (
                s.execute(
                    select(TopicPackageItemProto).where(
                        TopicPackageItemProto.ref_type == "catalog_entry"
                    )
                )
                .scalars()
                .all()
            )
            present = {
                c.catalog_code
                for c in s.execute(select(CatalogEntryProto)).scalars().all()
            }
            return [r.ref_id for r in rows if r.ref_id not in present]

        assert dangling_catalog_refs() == ["ghost-catalog"], "守卫应精确报出悬挂目录引用"

        # 删父目录 → 演示「无 FK 时删父不级联」，item 成孤儿，证明需应用层编排兜底
        s.delete(hit)
        s.commit()
        still_referencing = (
            s.execute(
                select(TopicPackageItemProto).where(
                    TopicPackageItemProto.ref_type == "catalog_entry",
                    TopicPackageItemProto.ref_id == "medical-aid",
                )
            )
            .scalars()
            .all()
        )
        assert len(still_referencing) == 1, (
            "无 FK 时删目录不级联，item 成孤儿 → 必须应用层守卫兜底"
        )
    print(
        "  [case 4] 多态 ref 无法单建 FK；catalog_entry 收录后可命中，"
        "应用层守卫精确报悬挂引用，删父不级联=需编排兜底"
    )


def main() -> int:
    print("数据模型参照完整性原型（设计层 PoC，非生产）")
    case_a_fk_cascade()
    case_b_business_code_needs_unique()
    case4_polymorphic_ref_and_catalog_enrollment()
    print("ALL PROTOTYPE ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
