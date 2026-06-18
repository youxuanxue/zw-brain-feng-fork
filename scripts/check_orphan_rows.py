#!/usr/bin/env python3
"""check_orphan_rows.py — preflight 段 67（数据模型参照完整性·方案脊柱 §六）.

产品保证：「zw-brain 永不留孤儿行——删父级联或拒绝，由系统机制强制」。
本守卫覆盖**下方常量枚举登记的** A/B/C 三类父子边（单一事实源 = 下方 *_EDGES，
**非 schema 自动反射**；新增父子边须在此登记才被覆盖）。覆盖范围 = 登记边集合，
不等于"模型里一切引用列"——未登记的松散可选引用（无 live deref、无 FK）刻意不纳入，
见 design §六.1 + §2.5：

  1. **孤儿扫描（枚举边）**：对 A/B/C 三类登记的父子边逐条 `NOT EXISTS` 扫孤儿子行。
     - A 类 14 + B 类 5（复合）= 19 条已建 FK + CASCADE（M1 + D50/C2 + D50/C5），DB 已兜底；
       本守卫仍扫作回潮哨兵（FK 被摘也能查出孤儿）。
     - C 类 9 条边无 FK（M2 honest 降级，父写子时不保证存在，见 design §2.5），
       **本守卫是其唯一参照完整性兜底**。
     - 任一边孤儿 > 0 → FAIL。
  2. **FK 回潮断言**：`Base.metadata` 的 FK 列数须 ≥ 已落地边数（24 = A14 + B5×2 复合），
     防 FK 被悄摘退回字符串引用（设计 §六.2）。
  3. **catalog_entry 可达性**：`topic_package_item(ref_type=catalog_entry)` 的 `ref_id`
     须都在 `catalog_entry`（按 tenant_id+catalog_code）命中；悬挂引用 → FAIL（§六.3）。

**自建干净 seed 库**：默认在临时目录 drop&recreate schema + 跑标准 seed
（`DatabaseStore().initialize()`），扫完即弃——CI 可跑、便宜、不需真库、不污染本地库。
传 `--db-path <path>` 可对指定库（如真实 seed 库）做一次性体检（M5 用）。

Exit：0 = 干净（无孤儿 + FK 未退化 + 无悬挂目录引用）；1 = 有违规。
Usage:
    ./scripts/check_orphan_rows.py            # 自建干净 seed 库扫
    ./scripts/check_orphan_rows.py --db-path .data/zw_brain.db   # 体检指定库
    ./scripts/check_orphan_rows.py --verbose
接入：scripts/preflight.sh 段 67
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from sqlalchemy import text  # noqa: E402

# ---------------------------------------------------------------------------
# 父子边定义（单一事实源）。A/B 类与 M1 的 FK 一致；C 类是 M2 降级后的守卫专属边。
# 每条边：child_table, child_col(s), parent_table, parent_col(s)。
# 单列边 child_col/parent_col 为 str；复合边为 tuple。
# ---------------------------------------------------------------------------

# A 类 12 条：子.列 → 父.id（M1 已建 FK + CASCADE）。
A_CLASS_EDGES: list[tuple[str, str, str, str]] = [
    ("approval_step", "approval_case_id", "approval_case", "id"),
    ("approval_decision", "step_id", "approval_step", "id"),
    ("objection_evidence", "objection_id", "objection_case", "id"),
    ("objection_process", "objection_id", "objection_case", "id"),
    ("objection_evaluation", "objection_id", "objection_case", "id"),
    ("form_section", "form_schema_id", "form_schema", "id"),
    ("form_field", "form_schema_id", "form_schema", "id"),
    ("form_validator", "form_schema_id", "form_schema", "id"),
    ("approval_flow_node", "schema_id", "approval_flow_schema", "id"),
    ("approval_flow_selection_rule", "schema_id", "approval_flow_schema", "id"),
    ("approval_flow_branch", "schema_id", "approval_flow_schema", "id"),
    ("recommendation_rule_clause", "rule_id", "recommendation_rule", "id"),
    # 国家通道（D50/C2）：资源网关凭据 → 资源申请单（apply_id 真实语义），删父级联删凭据。
    ("national_resource_credential", "application_id", "application_record", "id"),
    # 国家扩展要素（D50/C5）：编制任务 → 基本要素目录，删基本要素目录级联删编制任务。
    # basic_elem_catalog_id nullable（真实库 required=false），NULL 子列视为不引用、不算孤儿。
    ("national_ext_elem_compile_task", "basic_elem_catalog_id", "national_basic_elem_catalog", "id"),
]

# B 类 5 条复合边：子.(tenant_id,package_code) → topic_package.(tenant_id,package_code)
# （M1 已建复合 FK + CASCADE）。
B_CLASS_EDGES: list[tuple[str, tuple[str, str], str, tuple[str, str]]] = [
    (t, ("tenant_id", "package_code"), "topic_package", ("tenant_id", "package_code"))
    for t in (
        "topic_package_item",
        "topic_package_visibility",
        "topic_package_review_record",
        "topic_package_evidence",
        "topic_package_metric_projection",
    )
]

# C 类 9 条边：业务码引用，M2 honest 降级（无 FK）→ 本守卫是唯一兜底（design §2.5）。
# （末两条 catalog_item/delivery_subscription.resource_code 系 D48 amendment 补边，原裸奔。）
# 这些边按业务码匹配父行；空/NULL 子列视为「不引用」跳过，不算孤儿。
#
# **多态码列豁免前缀**（M5 真库实证，design §2.6）：部分 C 类码列是**多态主体码**，
# 不只指本边父表——同列也装别域 id。这类行**不是孤儿**（按设计无本边父行），
# 强行当孤儿清理会删合法数据、强行建 FK 会拒合法导入。故按前缀豁免，把完整性
# 主张**精确收敛到真该有本边父行的子集**（诚实，不假装也不漏报）：
#   - approval_case.application_code: `resource-review:*` = 资源评审主体（非申请单），无 application_record 父。
#   - delivery_attempt / delivery_execution_evidence.delivery_code: `materialize:*` = 物化作业 id
#     （非交付任务），无 delivery_task 父。
# 注：delivery_attempt 还有少量「父 subscribe_job 被删/缺位」的**真孤儿**（非多态码），
#     由 legacy pipelines mapper 导入末尾 _sweep_orphan_attempts 删子清理（design §2.6），
#     不靠本豁免遮盖。
# 每条边可选第 5 元素 = 豁免前缀元组（子码以该前缀开头 → 跳过，不计孤儿）。
C_CLASS_EDGES: list[tuple] = [
    ("delivery_receipt", "delivery_code", "delivery_task", "delivery_code"),
    ("delivery_attempt", "delivery_code", "delivery_task", "delivery_code", ("materialize:",)),
    ("delivery_subscription", "delivery_code", "delivery_task", "delivery_code"),
    ("delivery_execution_evidence", "delivery_code", "delivery_task", "delivery_code", ("materialize:",)),
    ("delivery_task", "application_code", "application_record", "application_code"),
    ("approval_case", "application_code", "application_record", "application_code", ("resource-review:",)),
    ("catalog_entry_version", "catalog_code", "catalog_entry", "catalog_code"),
    # 补边（D48 amendment）：两条 resource_code 软引用，过去裸奔——子表 nullable 码列
    # 引用 resource_asset.resource_code，无 FK（M2 honest 降级），本守卫兜底。NULL 跳过。
    ("catalog_item", "resource_code", "resource_asset", "resource_code"),
    ("delivery_subscription", "resource_code", "resource_asset", "resource_code"),
    # D62 D1/D2: 角色绑定不得指向不存在的 actor。external_actor_id 在身份认领时会被 rekey
    # （claim_legacy_actor_by_iaf 同事务搬移 binding），单列对 actor_projection 复合唯一键
    # (tenant_id, external_actor_id) 做硬 FK+CASCADE 在 SQLite 上时序受限——按 D48 §2.5
    # honest-downgrade 走 C 类守卫兜底（枚举孤儿=0），与 delivery/catalog 软引用边同范式。
    ("actor_org_role_binding", "external_actor_id", "actor_projection", "external_actor_id"),
]

# 已落地 FK 列数下限（A 类 14 单列 + B 类 5 复合×2 列 = 24）。
# （A 类含国家通道 national_resource_credential.application_id D50/C2 +
#  national_ext_elem_compile_task.basic_elem_catalog_id D50/C5。）
FK_FLOOR = 24


def _orphan_count_single(
    session,
    child: str,
    child_col: str,
    parent: str,
    parent_col: str,
    exclude_prefixes: tuple[str, ...] = (),
) -> int:
    """子表非空引用列在父表无命中的行数（NULL/空串视为不引用，不算孤儿）。

    exclude_prefixes：子码以这些前缀开头 → 多态主体码非本边引用，跳过不计孤儿
    （design §2.6 真库实证豁免）。
    """
    where_extra = ""
    params: dict[str, str] = {}
    for i, pfx in enumerate(exclude_prefixes):
        where_extra += f" AND c.{child_col} NOT LIKE :pfx{i}"
        params[f"pfx{i}"] = f"{pfx}%"
    sql = text(
        f"SELECT COUNT(*) FROM {child} c "
        f"WHERE c.{child_col} IS NOT NULL AND c.{child_col} != ''{where_extra} "
        f"AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{parent_col} = c.{child_col})"
    )
    return int(session.execute(sql, params).scalar() or 0)


def _orphan_count_composite(
    session, child: str, child_cols: tuple[str, str], parent: str, parent_cols: tuple[str, str]
) -> int:
    c0, c1 = child_cols
    p0, p1 = parent_cols
    sql = text(
        f"SELECT COUNT(*) FROM {child} c "
        f"WHERE c.{c0} IS NOT NULL AND c.{c1} IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{p0} = c.{c0} AND p.{p1} = c.{c1})"
    )
    return int(session.execute(sql).scalar() or 0)


def _catalog_entry_dangling(session) -> int:
    """topic_package_item(ref_type=catalog_entry) 的 ref_id 在 catalog_entry 无命中数（§六.3）。

    catalog_entry 主键是 surrogate id，自然键是 (tenant_id, catalog_code)；item.ref_id
    是 catalog_code。按 tenant 内 catalog_code 匹配。悬挂 = 引用了却未录入主表。
    """
    sql = text(
        "SELECT COUNT(*) FROM topic_package_item i "
        "WHERE i.ref_type = 'catalog_entry' AND i.ref_id IS NOT NULL AND i.ref_id != '' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM catalog_entry e "
        "  WHERE e.catalog_code = i.ref_id AND e.tenant_id = i.tenant_id"
        ")"
    )
    return int(session.execute(sql).scalar() or 0)


def _check_fk_floor() -> tuple[bool, int]:
    from zw_brain.domain import models  # noqa: F401  (注册 Base.metadata)
    from zw_brain.shared.db import Base

    fk_cols = [fk for t in Base.metadata.tables.values() for fk in t.foreign_keys]
    return (len(fk_cols) >= FK_FLOOR, len(fk_cols))


def _build_clean_seed_session(tmp_path: Path):
    """drop&recreate schema + 标准 seed，返回 (SessionLocal, cleanup)。"""
    import os

    os.environ["ZW_BRAIN_DB_PATH"] = str(tmp_path / "orphan_scan_seed.db")
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as db_module
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    ensure_runtime_schema()
    DatabaseStore().initialize()  # 标准 seed（与运行时同源）
    return db_module.create_session_factory()


def _open_session_for_path(db_path: str):
    import os

    os.environ["ZW_BRAIN_DB_PATH"] = db_path
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as db_module

    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    return db_module.create_session_factory()


def main() -> int:
    ap = argparse.ArgumentParser(description="孤儿行 + FK 回潮 + catalog 可达性守卫（段 67）")
    ap.add_argument(
        "--db-path",
        help="对指定库做体检（M5 真实 seed 库）；默认自建干净 seed 库扫",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    violations: list[str] = []

    # (1+3) 孤儿 + catalog 可达性：需要一个库
    tmpdir: tempfile.TemporaryDirectory | None = None
    if args.db_path:
        if not Path(args.db_path).exists():
            print(f"[orphan-rows] FAIL: --db-path 不存在：{args.db_path}", file=sys.stderr)
            return 1
        SessionLocal = _open_session_for_path(args.db_path)
        scope = f"指定库 {args.db_path}"
    else:
        tmpdir = tempfile.TemporaryDirectory()
        SessionLocal = _build_clean_seed_session(Path(tmpdir.name))
        scope = "自建干净 seed 库"

    try:
        with SessionLocal() as session:
            for edge in list(A_CLASS_EDGES) + C_CLASS_EDGES:
                child, ccol, parent, pcol = edge[0], edge[1], edge[2], edge[3]
                excl = edge[4] if len(edge) > 4 else ()
                n = _orphan_count_single(session, child, ccol, parent, pcol, excl)
                excl_note = f"（豁免前缀 {','.join(excl)}）" if excl else ""
                if n > 0:
                    violations.append(f"孤儿: {child}.{ccol} → {parent}.{pcol}{excl_note}: {n} 行无父")
                elif args.verbose:
                    print(f"  ok: {child}.{ccol} → {parent}.{pcol}{excl_note}: 0 孤儿")
            for child, ccols, parent, pcols in B_CLASS_EDGES:
                n = _orphan_count_composite(session, child, ccols, parent, pcols)
                if n > 0:
                    violations.append(
                        f"孤儿: {child}.{'+'.join(ccols)} → {parent}.{'+'.join(pcols)}: {n} 行无父"
                    )
                elif args.verbose:
                    print(f"  ok: {child}.({'+'.join(ccols)}) → {parent}: 0 孤儿")

            dangling = _catalog_entry_dangling(session)
            if dangling > 0:
                violations.append(
                    f"catalog 可达性: topic_package_item(ref_type=catalog_entry) "
                    f"有 {dangling} 条 ref_id 未录入 catalog_entry 主表（§六.3 悬挂引用）"
                )
            elif args.verbose:
                print("  ok: catalog_entry 可达性: 无悬挂引用")
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()

    # (2) FK 回潮断言（不需库，读 metadata）
    fk_ok, fk_n = _check_fk_floor()
    if not fk_ok:
        violations.append(
            f"FK 回潮: metadata FK 列数 {fk_n} < 下限 {FK_FLOOR}"
            "（A 类 14 + B 类复合 10）—— FK 被摘除，参照完整性退化"
        )
    elif args.verbose:
        print(f"  ok: FK 列数 {fk_n} ≥ {FK_FLOOR}")

    if violations:
        print(f"[orphan-rows] FAIL（{scope}）：", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\n产品保证「永不留孤儿行」被破坏。修复方向："
            "\n  - A/B 类孤儿：FK 被摘或 CASCADE 失效，复查 models.py。"
            "\n  - C 类孤儿：删父未级联删子（无 FK），需在 zw_brain/adapters/legacy/ "
            "或 domain 仓储删除路径补编排，或补父行。"
            "\n  - 悬挂目录引用：被引目录未录入 catalog_entry（缺陷 4，立项 J1 补录）。",
            file=sys.stderr,
        )
        return 1

    print(
        f"[orphan-rows] OK（{scope}）：A{len(A_CLASS_EDGES)}+B{len(B_CLASS_EDGES)}+C{len(C_CLASS_EDGES)} "
        f"条父子边孤儿=0，FK 列数 {fk_n}≥{FK_FLOOR}，catalog_entry 无悬挂引用。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
