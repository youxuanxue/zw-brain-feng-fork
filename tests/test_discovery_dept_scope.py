"""部门数据隔离 A2（M5 申请 mine + 部门收口 / M6 审批 R11）—— 单测。

锁定三件事，全部走真实库 enrich（temp_db 空 schema 自 seed，CI 内可跑）：

1. **mine（按个人 id）**：申请卡 ``mine`` = (payload['applicant'] == caller_actor)。
   关键不变量：取**未脱敏**的原始 payload.applicant（applicant 显示字段已 mask_default
   脱敏，拿它比对会恒不等）；caller_actor 空/None → 全 False。

2. **requests 部门收口**：visible_org_codes={orgA} → 仅 applicant_org∈orgA 的单成卡；
   None → 全量；空集 → 空（fail-closed）。mine 与部门过滤正交（管理员自家单两者同真）。

3. **approvals R11**：审批卡按 application_code 映到同 snapshot 已先行 enrich 的申请卡
   providerOrgCode，visible_org_codes={orgA} → 仅 provider=orgA 的审批单存活；映射缺失
   → fail-closed drop；None → 全量；空集 → 空。

seed 形态贴合真实写路径：applicant_org 由 ``applicantDept`` 落（ApplicationRepository
upsert），provider 机构码运行时单存 payload['owner_org_code']、legacy 单存
payload['provider_org_id']（两源都覆盖）。机构投影 seed 平表（复现真库 parent 全空）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from zw_brain.domain.discovery_snapshot_projection import (
    enrich_approvals_snapshot,
    enrich_requests_snapshot,
)
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.approval import ApprovalRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"

# 机构码：orgA = 受测部门角色所属机构；orgB = 无关机构（应被部门过滤排除）。
ORG_A = "11370000MB284651XL"
ORG_B = "36010000876"
ORG_A_NAME = "省大数据局"   # orgA 的机构名（验 applicant_org 存名时归一到码）
ORG_B_NAME = "别家单位"

ACTOR_ME = "zhangsan-001"   # 当前登录个人 id
ACTOR_OTHER = "lisi-002"    # 另一个人


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    """空 schema、无参考数据注入 —— enrich 真空起点（同 test_discovery_snapshot_projection）。"""
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "dept_scope.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_orgs() -> None:
    """机构投影平表（无父子，复现真库 parent_org_code 全空）。"""
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_A, "org_name": ORG_A_NAME}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_B, "org_name": ORG_B_NAME}, tenant_id=TENANT)


def _seed_application(
    app_id: str,
    *,
    applicant_dept: str,
    applicant: str | None = None,
    owner_org_code: str | None = None,
    provider_org_id: str | None = None,
    kind: str | None = "apply",
    resource_name: str = "人口库接口",
    status: str = "submitted",
) -> None:
    """落一张申请单：applicantDept→applicant_org（部门过滤源）、applicant→mine 源、
    owner_org_code/provider_org_id→providerOrgCode（R11 owner 源）。"""
    request: dict[str, object] = {
        "id": app_id,
        "status": status,
        "applicant": applicant if applicant is not None else "张三",
        "applicantDept": applicant_dept,
        "kind": kind,
        "resource_name": resource_name,
        "resourceId": f"res-{app_id}",
        "use_reason": "办理业务",
    }
    if owner_org_code is not None:
        request["owner_org_code"] = owner_org_code
    if provider_org_id is not None:
        request["provider_org_id"] = provider_org_id
    ApplicationRepository().upsert_from_request(request, tenant_id=TENANT)


def _seed_approval_case(app_id: str, status: str = "pending") -> None:
    """为已落的申请单补审批 case（application_code == app_id）。"""
    ApprovalRepository().upsert_from_request_and_approval(
        {"id": app_id, "status": status}, {}, tenant_id=TENANT
    )


# ── Part 1a — mine 标记（按个人 id；取未脱敏 payload.applicant）─────────────────

def test_mine_true_when_applicant_matches_caller(temp_db: Path) -> None:
    _seed_orgs()
    _seed_application("APP-MINE", applicant_dept=ORG_A, applicant=ACTOR_ME)
    _seed_application("APP-OTHER", applicant_dept=ORG_A, applicant=ACTOR_OTHER)

    out = enrich_requests_snapshot({"requests": []}, tenant_id=TENANT, caller_actor=ACTOR_ME)
    by_id = {r["id"]: r for r in out["requests"]}
    assert by_id["APP-MINE"]["mine"] is True, "payload.applicant == caller_actor → mine"
    assert by_id["APP-OTHER"]["mine"] is False, "别人提的单 → 非 mine"


def test_mine_reads_unmasked_payload_not_display_field(temp_db: Path) -> None:
    """mine 必须比对未脱敏的 payload.applicant —— applicant 显示字段已 mask_default 脱敏。"""
    _seed_orgs()
    _seed_application("APP-MASK", applicant_dept=ORG_A, applicant=ACTOR_ME)
    out = enrich_requests_snapshot({"requests": []}, tenant_id=TENANT, caller_actor=ACTOR_ME)
    card = next(r for r in out["requests"] if r["id"] == "APP-MASK")
    assert card["mine"] is True, "未脱敏 payload.applicant 命中 → mine（不被脱敏显示字段误判）"
    # 自证前提：显示字段确已脱敏（与原始 applicant 不等），否则本测无意义。
    assert card["applicant"] != ACTOR_ME, "applicant 显示字段应已脱敏，证明 mine 没读它"


def test_mine_all_false_when_caller_actor_empty(temp_db: Path) -> None:
    _seed_orgs()
    _seed_application("APP-1", applicant_dept=ORG_A, applicant=ACTOR_ME)
    _seed_application("APP-2", applicant_dept=ORG_A, applicant=ACTOR_OTHER)
    for caller in ("", None):
        out = enrich_requests_snapshot({"requests": []}, tenant_id=TENANT, caller_actor=caller)
        assert all(r["mine"] is False for r in out["requests"]), (
            f"caller_actor={caller!r} → 不主张任何单是「我的」"
        )


# ── Part 1b — requests 部门收口（applicant_org ∈ visible）───────────────────────

def test_requests_dept_scope_set_keeps_only_in_org(temp_db: Path) -> None:
    _seed_orgs()
    _seed_application("APP-A1", applicant_dept=ORG_A, applicant=ACTOR_ME)
    _seed_application("APP-A2", applicant_dept=ORG_A_NAME, applicant=ACTOR_OTHER)  # 存名 → 归一到码
    _seed_application("APP-B1", applicant_dept=ORG_B, applicant=ACTOR_OTHER)

    out = enrich_requests_snapshot(
        {"requests": []}, tenant_id=TENANT, visible_org_codes={ORG_A}, caller_actor=ACTOR_ME
    )
    ids = {r["id"] for r in out["requests"]}
    assert ids == {"APP-A1", "APP-A2"}, "仅 applicant_org∈{orgA} 成卡（名形态归一到码也命中）"
    assert "APP-B1" not in ids, "orgB 的单被部门过滤排除"


def test_requests_dept_scope_none_keeps_all(temp_db: Path) -> None:
    _seed_orgs()
    _seed_application("APP-A1", applicant_dept=ORG_A, applicant=ACTOR_ME)
    _seed_application("APP-B1", applicant_dept=ORG_B, applicant=ACTOR_OTHER)
    out = enrich_requests_snapshot(
        {"requests": []}, tenant_id=TENANT, visible_org_codes=None, caller_actor=ACTOR_ME
    )
    assert {r["id"] for r in out["requests"]} == {"APP-A1", "APP-B1"}, "None=全局放行全量"


def test_requests_dept_scope_empty_set_keeps_none(temp_db: Path) -> None:
    _seed_orgs()
    _seed_application("APP-A1", applicant_dept=ORG_A, applicant=ACTOR_ME)
    _seed_application("APP-B1", applicant_dept=ORG_B, applicant=ACTOR_OTHER)
    out = enrich_requests_snapshot(
        {"requests": []}, tenant_id=TENANT, visible_org_codes=set(), caller_actor=ACTOR_ME
    )
    assert out["requests"] == [], "空集=fail-closed → 空列表"


def test_mine_independent_of_dept_filter(temp_db: Path) -> None:
    """正交性：管理员自家单既 mine 又在本机构域内（两者同时为真，不互相抑制）。"""
    _seed_orgs()
    _seed_application("APP-OWN", applicant_dept=ORG_A, applicant=ACTOR_ME)
    out = enrich_requests_snapshot(
        {"requests": []}, tenant_id=TENANT, visible_org_codes={ORG_A}, caller_actor=ACTOR_ME
    )
    card = next(r for r in out["requests"] if r["id"] == "APP-OWN")
    assert card["mine"] is True, "自家单 mine"
    # 它同时通过了部门过滤（成卡即证），即 in-org 与 mine 并存。


# ── Part 2 — approvals R11（管理员只见自家机构作为提供方的审批单）────────────────

def _build_snapshot_with_requests(
    *, visible_org_codes: set[str] | None
) -> dict[str, object]:
    """先 enrich requests（让申请卡带上 providerOrgCode），再喂给 approvals enrich——
    复现 handler 顺序（requests 先于 approvals enrich 同一 snapshot）。"""
    return enrich_requests_snapshot(
        {"requests": []}, tenant_id=TENANT, visible_org_codes=visible_org_codes, caller_actor=ACTOR_ME
    )


def _seed_apps_and_approvals_two_providers() -> None:
    """两张审批单：APP-PA 提供方=orgA（运行时 owner_org_code），APP-PB 提供方=orgB（legacy
    provider_org_id）。applicant_org 一律 orgA 以隔离「申请方 vs 提供方」两轴——R11 收口的是
    提供方机构，不是申请方。"""
    _seed_application(
        "APP-PA", applicant_dept=ORG_A, applicant=ACTOR_ME, owner_org_code=ORG_A
    )
    _seed_application(
        "APP-PB", applicant_dept=ORG_A, applicant=ACTOR_OTHER, provider_org_id=ORG_B
    )
    _seed_approval_case("APP-PA")
    _seed_approval_case("APP-PB")


def test_approvals_r11_set_keeps_only_own_provider_org(temp_db: Path) -> None:
    _seed_orgs()
    _seed_apps_and_approvals_two_providers()
    # requests 在 None 域下 enrich（保留两张申请卡，让 approvals 能映到 provider）；
    # approvals 自身在 {orgA} 域下收口。
    snap = _build_snapshot_with_requests(visible_org_codes=None)
    out = enrich_approvals_snapshot(snap, tenant_id=TENANT, visible_org_codes={ORG_A})
    ids = {a["id"] for a in out["approvals"]}
    assert ids == {"APP-PA"}, "仅提供方=orgA 的审批单存活（orgB 提供方被 R11 排除）"


def test_approvals_r11_none_keeps_all(temp_db: Path) -> None:
    _seed_orgs()
    _seed_apps_and_approvals_two_providers()
    snap = _build_snapshot_with_requests(visible_org_codes=None)
    out = enrich_approvals_snapshot(snap, tenant_id=TENANT, visible_org_codes=None)
    assert {a["id"] for a in out["approvals"]} == {"APP-PA", "APP-PB"}, "None=全局放行全量"


def test_approvals_r11_empty_set_keeps_none(temp_db: Path) -> None:
    _seed_orgs()
    _seed_apps_and_approvals_two_providers()
    snap = _build_snapshot_with_requests(visible_org_codes=None)
    out = enrich_approvals_snapshot(snap, tenant_id=TENANT, visible_org_codes=set())
    assert out["approvals"] == [], "空集=fail-closed → 空列表"


# ── Part 2b — 入站单（别部门申请本部门数据）的供方可见性（集成期复核修正）──────────────
# A2 原把「applicant_org=orgB、provider=orgA 的单被 requests 按 applicant 过滤掉 → 审批 drop」
# 当成 fail-closed 正解，实为缺陷：orgA 是**提供方**、必须在审批队列看见并办理这张入站单。
# 修法 = requests 收口改 applicant OR provider 两侧；下列三测锁定修正后的正确语义。

def test_requests_dept_scope_keeps_provider_side_inbound(temp_db: Path) -> None:
    """别部门(orgB)申请本部门(orgA)数据的入站单：applicant_org=orgB 不在域内，但 provider=orgA
    在域内 → 对 orgA 部门角色必须保留（供方审批必须看得到）。mine=False（别人提的）。"""
    _seed_orgs()
    _seed_application("APP-IN", applicant_dept=ORG_B, applicant=ACTOR_OTHER, owner_org_code=ORG_A)
    out = enrich_requests_snapshot(
        {"requests": []}, tenant_id=TENANT, visible_org_codes={ORG_A}, caller_actor=ACTOR_ME
    )
    card = next((r for r in out["requests"] if r["id"] == "APP-IN"), None)
    assert card is not None, "provider=orgA 的入站申请单对 orgA 可见（applicant OR provider 收口）"
    assert card["mine"] is False, "别人提的入站单非 mine"


def test_approvals_r11_provider_sees_inbound_request_approval(temp_db: Path) -> None:
    """供方 R11 正路：orgB 申请 orgA 数据 → orgA 部门管理员在审批队列看得到、能办。
    与 requests 两侧收口配套：申请卡留住 → 审批可映射 provider=orgA → 留存。"""
    _seed_orgs()
    _seed_application("APP-IN", applicant_dept=ORG_B, applicant=ACTOR_OTHER, owner_org_code=ORG_A)
    _seed_approval_case("APP-IN")
    snap = _build_snapshot_with_requests(visible_org_codes={ORG_A})
    assert "APP-IN" in {r["id"] for r in snap["requests"]}, "前提：入站申请卡因 provider∈域被留住"
    out = enrich_approvals_snapshot(snap, tenant_id=TENANT, visible_org_codes={ORG_A})
    assert {a["id"] for a in out["approvals"]} == {"APP-IN"}, "供方=orgA 的审批单 orgA 看得到"


def test_approvals_r11_unrelated_request_fail_closed_drop(temp_db: Path) -> None:
    """真·fail-closed：申请与本部门毫无关系（applicant=orgB 且 provider=orgB）→ 申请卡被
    requests 两侧收口都排除 → 审批映射缺失 → drop（不泄漏与本部门无关的审批单）。"""
    _seed_orgs()
    _seed_application("APP-UNREL", applicant_dept=ORG_B, applicant=ACTOR_OTHER, owner_org_code=ORG_B)
    _seed_approval_case("APP-UNREL")
    snap = _build_snapshot_with_requests(visible_org_codes={ORG_A})
    assert "APP-UNREL" not in {r["id"] for r in snap["requests"]}, "前提：与 orgA 无关 → 申请卡被过滤"
    out = enrich_approvals_snapshot(snap, tenant_id=TENANT, visible_org_codes={ORG_A})
    assert out["approvals"] == [], "无关审批单 → fail-closed drop"
