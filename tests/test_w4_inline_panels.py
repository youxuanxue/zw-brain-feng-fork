"""W4 散件波次 contract test.

W4 不增加 skill，只把现有 skill 拼成 inline form/panel 落到 5 个角色的
现有 P-page。本测试验证：
- 每个角色的 inline panel 被正确加进 pages.js（按角色 STATE.role 隔离）
- 每个 inline action 被加进 app.js 的 ACTIONS，调用对应已有 skill
- 不破坏既有 提供方部门 / 业务运营员 / 安全审计员/r6ProviderWorkflowCards / W2/W3 的 wiring
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (REPO / "zw-brain-web" / "js" / name).read_text(encoding="utf-8")


def test_w4_1_r2_grade_authorization_form_present() -> None:
    pages = _read("pages.js")
    assert "r2GradeAuthorizationStrategyForm" in pages
    # role gate
    assert "window.STATE.role !== 'ROLE_ORGAN_MANAGER'" in pages
    # form fields
    for el_id in ("approval-grade", "approval-mask", "approval-freq", "approval-limitday", "approval-cascade"):
        assert el_id in pages, f"missing form field id {el_id}"


def test_w4_1_approveRequest_passes_grade_policy() -> None:
    app = _read("app.js")
    assert "grade_policy" in app
    assert "approval-grade" in app and "approval-mask" in app
    # still calls existing skill, not a new one
    assert "application.resource.review" in app


def test_w4_4_r5_summary_withdraw_panel_and_action() -> None:
    pages = _read("pages.js")
    app = _read("app.js")
    assert "r5SummaryWithdrawAction" in pages
    assert "window.STATE.role !== 'ROLE_ORGAN_MANAGER'" in pages
    assert "withdrawSummary" in app
    # uses existing summary.confirm skill
    assert "summary.confirm" in app


def test_w4_4_r5_objection_four_substages_panel_and_actions() -> None:
    pages = _read("pages.js")
    app = _read("app.js")
    assert "r5ObjectionFourSubstagesPanel" in pages
    # 4 子段表单标题
    for label in ("① 评估", "② 处置", "③ 授权影响", "④ 用数反馈"):
        assert label in pages
    # 4 个 ACTIONS 对应 W1 已有 objection.case.* skill
    for action, skill in (
        ("evaluateObjection", "objection.case.evaluate"),
        ("processObjection", "objection.case.assign"),
        ("reviewObjectionAuthorization", "objection.case.review"),
        ("replyObjection", "objection.case.reply"),
    ):
        assert action in app, f"missing ACTION {action}"
        assert skill in app, f"missing skill ref {skill}"


def test_w4_5_r1_workbench_api_credentials_and_demand_registration() -> None:
    pages = _read("pages.js")
    app = _read("app.js")
    # panel 函数
    assert "r1ApiCredentialsAndDemandRegistration" in pages
    assert "window.STATE.role !== 'ROLE_ORGAN_OPERATER'" in pages
    assert "我的 API 凭据" in pages
    assert "需求登记前置" in pages
    # 提交需求登记的 ACTION 走 require.intent.submit
    assert "submitDemandRegistration" in app
    assert "require.intent.submit" in app
    # 表单 input id
    for el_id in ("apply-demand-purpose", "apply-demand-fields", "apply-demand-window"):
        assert el_id in pages


def test_w4_2_r8_bypass_surveillance_panel_wired() -> None:
    pages = _read("pages.js")
    app = _read("app.js")
    assert "r8BypassSurveillancePanel" in pages
    assert "window.STATE.role !== 'ROLE_SECURITY_AUDIT'" in pages
    # 复用 W1.3 direct_access.delivery.list
    assert "RUNTIME_R8_DIRECT_ACCESS" in pages
    assert "direct_access.delivery.list" in app
    # P6 路由对 安全审计员 时预拉
    assert "roleCan(['ROLE_SECURITY_AUDIT'])" in app


def test_w4_3_grassroots_filter_and_exception_callback() -> None:
    pages = _read("pages.js")
    app = _read("app.js")
    # 基层填报人 only 看 supplementing / need-fix 状态
    assert "isGrassroots" in pages
    assert "supplementing" in pages
    assert "need-fix" in pages
    # 异常回传 ACTION 走 supplement.submit
    assert "openGrassrootsExceptionForm" in app
    assert "supplement.submit" in app
    assert "exception_callback" in app


def test_w4_does_not_register_new_skills() -> None:
    """Sanity: W4 itself is pure UI inline work — no new manifests from that
    feature. Post-W4 work (QUICKSTART business smoke) legitimately added 6 new
    skill manifests (grant.suspend/revoke, service.rating.submit, ops.ticket.*,
    ops.shift_handover.submit). Lock the count at the current baseline so a
    future W4-style "UI-only" feature can't quietly add a new skill manifest."""
    manifest_dir = REPO / "zw_brain" / "skill_registration" / "registered"
    # W3 baseline: 192 manifests; Phase 5 (post-W4) added 6 for the smoke flow → 198.
    # 2026-05-19 retrofit: +2 for J1 凭据领取闭环（credential.issue / credential.query）→ 200.
    count = sum(1 for p in manifest_dir.glob("*.json"))
    assert count == 200, f"unexpected skill manifest count change; count = {count}"
    # spot-check: W2 added catalog.entry.reverse_draft.suggest
    assert (manifest_dir / "catalog.entry.reverse_draft.suggest.json").exists()
    # spot-check: Phase 5 added the 6 customer-facing business skills
    for name in (
        "application.grant.suspend",
        "application.grant.revoke",
        "service.rating.submit",
        "ops.ticket.create",
        "ops.ticket.close",
        "ops.shift_handover.submit",
    ):
        assert (manifest_dir / f"{name}.json").exists(), f"missing manifest: {name}"
