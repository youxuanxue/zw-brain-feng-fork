# Wave: 1
# Journey: J1
# Pages: P3 (供需对接段)
# Consumer-faces: API (repo-level)
# Roles: ROLE_BUSIAUDIT (主管部门需求汇总) | ROLE_ORGAN_OPERATER (申请方)
# Trace:
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j1-supply-demand-meta-merge.feature
#   zw_brain/domain/supply_demand_phase.py
#   zw_brain/domain/repositories/supply_demand.py
"""F4: J1 供需对接子流程 6 步实装 + meta 合并 + sd-default 真实需求历史回归.

数据隔离：realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据），
模板缺位时整模块 skip（承接旧 require_real_seed 数据量门槛语义），写不污染真实模板。
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)
from zw_brain.shared.db import get_database_url

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"

# 门槛语义（application_record≥100）由 realistic_pg_module 的 skip-when-absent 承接。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")


def _pg_read(sql: str, params: tuple = ()):
    """Read against the cloned realistic PG (app read-path's DB), never a file."""
    url = make_url(get_database_url())
    with psycopg.connect(
        host=url.host, port=url.port, user=url.username,
        password=url.password, dbname=url.database,
    ) as conn:
        return conn.execute(sql, params).fetchall()


@pytest.fixture(scope="module")
def repo():
    from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
    return SupplyDemandRepository()


# ──────────────────────────────────────────────────────────────────────
# 6 步状态机
# ──────────────────────────────────────────────────────────────────────

from zw_brain.domain.supply_demand_phase import (  # noqa: E402
    PHASE_GAP_DISCOVERED,
    PHASE_MANUAL_REGISTERED,
    PHASE_PROVIDER_RESPONDED,
    PHASE_RECOMMEND_FAILED,
    PHASE_REGISTERED,
    PHASE_SUBSCRIBED,
)


def _register(repo, demand_id: str, *, title="测试需求") -> dict:
    return repo.register_demand(
        demand_id=demand_id,
        title=title,
        applicant="U_OP",
        applicant_dept="部门A",
        tenant_id=TENANT,
    )


# 6 步 happy path（规则匹配命中：直接 REGISTERED → PROVIDER_RESPONDED → SUBSCRIBED）
def test_demand_phase_happy_path_recommend_hit(repo):
    demand = _register(repo, "F4-HAPPY-1")
    assert demand["demand_phase"] == PHASE_GAP_DISCOVERED
    repo.advance_phase("F4-HAPPY-1", PHASE_REGISTERED, tenant_id=TENANT)
    repo.advance_phase("F4-HAPPY-1", PHASE_PROVIDER_RESPONDED, tenant_id=TENANT)
    repo.advance_phase("F4-HAPPY-1", PHASE_SUBSCRIBED, tenant_id=TENANT)
    final = repo.get_demand("F4-HAPPY-1", tenant_id=TENANT)
    assert final is not None
    assert final["demand_phase"] == PHASE_SUBSCRIBED
    assert final["status"] == "effective"


# 6 步推荐失败转人工 path
def test_demand_phase_recommend_failed_manual_path(repo):
    _register(repo, "F4-MANUAL-1")
    repo.advance_phase("F4-MANUAL-1", PHASE_REGISTERED, tenant_id=TENANT)
    repo.advance_phase("F4-MANUAL-1", PHASE_RECOMMEND_FAILED, tenant_id=TENANT)
    repo.advance_phase("F4-MANUAL-1", PHASE_MANUAL_REGISTERED, tenant_id=TENANT)
    repo.advance_phase("F4-MANUAL-1", PHASE_PROVIDER_RESPONDED, tenant_id=TENANT)
    repo.advance_phase("F4-MANUAL-1", PHASE_SUBSCRIBED, tenant_id=TENANT)
    final = repo.get_demand("F4-MANUAL-1", tenant_id=TENANT)
    assert final["demand_phase"] == PHASE_SUBSCRIBED


@pytest.mark.parametrize(
    "target_phase",
    [PHASE_REGISTERED, PHASE_RECOMMEND_FAILED, PHASE_MANUAL_REGISTERED,
     PHASE_PROVIDER_RESPONDED, PHASE_SUBSCRIBED],
)
def test_demand_phase_each_reachable(repo, target_phase):
    """6 步每个 phase 从 gap_discovered 可达."""
    demand_id = f"F4-REACH-{target_phase}"
    _register(repo, demand_id)
    paths = {
        PHASE_REGISTERED: [PHASE_REGISTERED],
        PHASE_RECOMMEND_FAILED: [PHASE_REGISTERED, PHASE_RECOMMEND_FAILED],
        PHASE_MANUAL_REGISTERED: [PHASE_REGISTERED, PHASE_RECOMMEND_FAILED, PHASE_MANUAL_REGISTERED],
        PHASE_PROVIDER_RESPONDED: [PHASE_REGISTERED, PHASE_PROVIDER_RESPONDED],
        PHASE_SUBSCRIBED: [PHASE_REGISTERED, PHASE_PROVIDER_RESPONDED, PHASE_SUBSCRIBED],
    }[target_phase]
    for nxt in paths:
        repo.advance_phase(demand_id, nxt, tenant_id=TENANT)
    final = repo.get_demand(demand_id, tenant_id=TENANT)
    assert final["demand_phase"] == target_phase


def test_demand_phase_rejects_illegal_jump(repo):
    """gap_discovered 直接跳 provider_responded 拒（必须先 registered）."""
    from zw_brain.domain.supply_demand_phase import SupplyDemandPhaseError

    _register(repo, "F4-ILLEGAL")
    with pytest.raises(SupplyDemandPhaseError):
        repo.advance_phase("F4-ILLEGAL", PHASE_PROVIDER_RESPONDED, tenant_id=TENANT)


def test_demand_phase_subscribed_is_terminal(repo):
    from zw_brain.domain.supply_demand_phase import SupplyDemandPhaseError

    _register(repo, "F4-TERM")
    for nxt in (PHASE_REGISTERED, PHASE_PROVIDER_RESPONDED, PHASE_SUBSCRIBED):
        repo.advance_phase("F4-TERM", nxt, tenant_id=TENANT)
    with pytest.raises(SupplyDemandPhaseError):
        repo.advance_phase("F4-TERM", PHASE_REGISTERED, tenant_id=TENANT)


# ──────────────────────────────────────────────────────────────────────
# meta 合并 (Business Requirement)
# ──────────────────────────────────────────────────────────────────────


def test_business_requirement_meta_only(repo):
    """BR.payload 不含原始 application 业务字段拷贝（feature §scenario 3）."""
    _register(repo, "A101", title="户籍数据需求")
    _register(repo, "A102", title="户籍数据需求")
    _register(repo, "A103", title="户籍数据需求")
    br = repo.create_business_requirement(
        br_id="BR701",
        application_ids=["A101", "A102", "A103"],
        merge_reason="同主题：户籍数据，部门 A/B/C",
        merged_by="U_BUSIAUDIT",
        merged_by_role="ROLE_BUSIAUDIT",
        tenant_id=TENANT,
    )
    assert br["kind"] == "business_requirement"
    assert br["application_ids"] == ["A101", "A102", "A103"]
    assert br["merge_reason"]
    # meta-only：不允许出现 purpose / period / files 等业务字段拷贝
    for forbidden in ("purpose", "period", "files", "use_reason", "use_item"):
        assert forbidden not in br, f"BR 不应复制业务字段 {forbidden}"


def test_business_requirement_requires_busiaudit(repo):
    """ROLE_ORGAN_OPERATER 不能合并业务需求（feature §scenario 2）."""
    _register(repo, "A201", title="非授权合并")
    _register(repo, "A202", title="非授权合并")
    with pytest.raises(PermissionError):
        repo.create_business_requirement(
            br_id="BR-DENY",
            application_ids=["A201", "A202"],
            merge_reason="测试拒绝路径",
            merged_by="U_OP",
            merged_by_role="ROLE_ORGAN_OPERATER",
            tenant_id=TENANT,
        )


def test_business_requirement_status_dispatched_responded_evaluated(repo):
    """BR 状态流：dispatched → responded → evaluated (feature §scenario 1 末段)."""
    _register(repo, "A301", title="BR-状态-1")
    _register(repo, "A302", title="BR-状态-2")
    repo.create_business_requirement(
        br_id="BR-STATUS",
        application_ids=["A301", "A302"],
        merge_reason="状态机测试",
        merged_by="U_BUSIAUDIT",
        merged_by_role="ROLE_BUSIAUDIT",
        tenant_id=TENANT,
    )
    repo.update_business_requirement_status("BR-STATUS", "responded", tenant_id=TENANT)
    final = repo.update_business_requirement_status("BR-STATUS", "evaluated", tenant_id=TENANT)
    assert final["br_status"] == "evaluated"
    assert final["status"] == "effective"


def test_business_requirement_illegal_status_jump(repo):
    _register(repo, "A401", title="x")
    _register(repo, "A402", title="x")
    repo.create_business_requirement(
        br_id="BR-ILLEGAL", application_ids=["A401", "A402"], merge_reason="x",
        merged_by="U_BUSIAUDIT", merged_by_role="ROLE_BUSIAUDIT", tenant_id=TENANT,
    )
    with pytest.raises(ValueError):
        repo.update_business_requirement_status("BR-ILLEGAL", "evaluated", tenant_id=TENANT)


def test_business_requirement_application_withdrawn_removes_from_ids(repo):
    """原始申请撤回 → BR.application_ids 自动剔除 + 事件留痕 (feature §scenario 4)."""
    _register(repo, "A501", title="撤回 BR")
    _register(repo, "A502", title="撤回 BR")
    _register(repo, "A503", title="撤回 BR")
    repo.create_business_requirement(
        br_id="BR-WITHDRAW",
        application_ids=["A501", "A502", "A503"],
        merge_reason="原始撤回剔除测试",
        merged_by="U_BUSIAUDIT",
        merged_by_role="ROLE_BUSIAUDIT",
        tenant_id=TENANT,
    )
    after = repo.remove_application_from_business_requirement(
        "BR-WITHDRAW", "A502", reason="申请人撤回 at 2026-05-24", tenant_id=TENANT,
    )
    assert after["application_ids"] == ["A501", "A503"]
    events = after["events"]
    assert len(events) == 1
    assert events[0]["event"] == "application_removed"
    assert events[0]["application_id"] == "A502"
    assert "申请人撤回" in events[0]["reason"]


def test_business_requirement_min_two_ids(repo):
    _register(repo, "A_ONLY", title="x")
    with pytest.raises(ValueError):
        repo.create_business_requirement(
            br_id="BR-SINGLE",
            application_ids=["A_ONLY"],
            merge_reason="不应允许 1 个",
            merged_by="U_BUSIAUDIT",
            merged_by_role="ROLE_BUSIAUDIT",
            tenant_id=TENANT,
        )


# ──────────────────────────────────────────────────────────────────────
# 国家通道占位 (feature §scenario 5)
# ──────────────────────────────────────────────────────────────────────


def test_national_channel_placeholder(repo):
    """channel_class=national 仅标记，Wave 1 不实施国家直达完整流程."""
    demand = repo.register_demand(
        demand_id="F4-NATIONAL",
        title="需求 - 国家直达",
        applicant="U_OP",
        applicant_dept="部门X",
        tenant_id=TENANT,
        channel_class="national",
    )
    assert demand["channel_class"] == "national"
    # phase 仍按 6 步推进，但 channel_class 标记可让 UI 显示占位提示


# ──────────────────────────────────────────────────────────────────────
# 规则匹配（Wave 1，AI 推荐归 E3 Wave 2）
# ──────────────────────────────────────────────────────────────────────


def test_cluster_similar_demands_by_title_prefix(repo):
    demands = [
        {"id": "D1", "title": "户籍数据需求-部门A", "target_resource_hint": "C700"},
        {"id": "D2", "title": "户籍数据需求-部门B", "target_resource_hint": "C700"},
        {"id": "D3", "title": "其他主题", "target_resource_hint": "C800"},
    ]
    clusters = repo.cluster_similar_demands(demands, title_prefix_len=4)
    # 户籍数据 前 4 字相同 + 同 hint 归一簇
    found_cluster_sizes = sorted(len(c) for c in clusters)
    assert found_cluster_sizes == [1, 2]


def test_find_resource_match_returns_hit(repo):
    catalog_titles = ["户籍登记信息库", "医保码信息库", "异地就医统筹区开通信息"]
    hit = repo.find_resource_match("户籍登记", None, catalog_titles=catalog_titles)
    assert hit == "户籍登记信息库"
    miss = repo.find_resource_match("某个不在库里的需求", None, catalog_titles=catalog_titles)
    assert miss is None


# ──────────────────────────────────────────────────────────────────────
# sd-default 真实需求历史回归（不写）
# ──────────────────────────────────────────────────────────────────────


def test_real_dump_require_demand_distribution_present():
    """sd-default 真实数据：require + original_require 共 ≥150 条；apply 与之独立."""
    require_cnt = 0
    original_cnt = 0
    apply_cnt = 0
    for (pj,) in _pg_read(
        "SELECT payload_json FROM application_record WHERE tenant_id=%s", (TENANT,)
    ):
        try:
            p = json.loads(pj) if isinstance(pj, str) else pj
        except Exception:
            continue
        kind = (p or {}).get("kind")
        if kind == "require":
            require_cnt += 1
        elif kind == "original_require":
            original_cnt += 1
        elif kind == "apply":
            apply_cnt += 1
    assert require_cnt + original_cnt >= 150, f"require+original_require {require_cnt+original_cnt}"
    assert apply_cnt >= 50, f"apply {apply_cnt}"


def test_real_dump_cluster_top_5_titles_have_dupes(repo):
    """规则聚类：真实数据中 ≥1 簇 size ≥ 4（佐证 BR 合并的业务必要性）."""
    demands: list[dict] = []
    for (pj,) in _pg_read(
        "SELECT payload_json FROM application_record WHERE tenant_id=%s", (TENANT,)
    ):
        try:
            p = json.loads(pj) if isinstance(pj, str) else pj
        except Exception:
            continue
        if (p or {}).get("kind") in ("require", "original_require"):
            demands.append({"title": (p or {}).get("title") or "", "target_resource_hint": ""})
    clusters = repo.cluster_similar_demands(demands, title_prefix_len=6)
    largest = max((len(c) for c in clusters), default=0)
    assert largest >= 4, f"expected ≥1 cluster size >=4, got max={largest}"


# ──────────────────────────────────────────────────────────────────────
# 边界 — 不影响原始 application 审批状态机 (feature §scenario regression)
# ──────────────────────────────────────────────────────────────────────


def test_business_requirement_does_not_mutate_original_applications(repo):
    """合并 / BR 状态推进都不改原始 application 的 status."""
    from zw_brain.domain.repositories.application import ApplicationRepository
    app_repo = ApplicationRepository()
    a601 = _register(repo, "A601", title="不互窜")
    a602 = _register(repo, "A602", title="不互窜")
    repo.create_business_requirement(
        br_id="BR-ISOLATE",
        application_ids=["A601", "A602"],
        merge_reason="隔离测试",
        merged_by="U_BUSIAUDIT",
        merged_by_role="ROLE_BUSIAUDIT",
        tenant_id=TENANT,
    )
    repo.update_business_requirement_status("BR-ISOLATE", "responded", tenant_id=TENANT)
    repo.update_business_requirement_status("BR-ISOLATE", "evaluated", tenant_id=TENANT)
    # 原始 application 应仍为 submitted（register_demand 写入 status）
    records = {r.application_code: r for r in app_repo.list_records(tenant_id=TENANT)}
    assert records["A601"].status == "submitted"
    assert records["A602"].status == "submitted"
