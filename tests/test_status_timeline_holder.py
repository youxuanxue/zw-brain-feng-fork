"""status_timeline 逐运行时态 (当前段, holder) 回归锁 —— #280 脊柱「卡在谁桌上」防回潮。

补录态(supplementing)曾被误标「审核中·卡在受理台·业务运营员（受理）」——已审批单退错一格 +
指错人，且专设的基层补录 holder 锁在运行时永不写的 approved/in_delivery 后面是死码。本测把
每个运行时 status 的当前段 + holder 钉死，防再回潮。纯函数级，不依赖 DB。
"""

import pytest

from zw_brain.domain.services.request_service import RequestService

pytestmark = pytest.mark.no_db

_REQ = {"id": "R", "providerOrgName": "省大数据局"}


def _current(status: str, delivery=None) -> dict:
    svc = RequestService.__new__(RequestService)  # status_timeline/_holder_for 纯函数，免 __init__
    rows = svc.status_timeline(dict(_REQ, status=status), delivery, perspective="applicant")
    return next((s for s in rows if s["status"] == "current"), {})


# (运行时 status, 当前段, holder)
_CASES = [
    ("submitted", "审核中", "业务运营员（受理）"),
    ("pending", "审核中", "业务运营员（受理）"),
    ("need-fix", "审核中", "申请人（待补正）"),
    ("dept_approved", "审批结论", "部门管理员·省大数据局"),
    ("supplementing", "交付", "镇街/村社区填报人（补录）"),  # ← 根治点
    ("summary-pending", "交付", ""),  # 待汇总确认：交付段、holder 诚实留空（汇总确认人未确证、不捏造）
    ("rejected", "审批结论", ""),
]


def test_holder_per_runtime_state() -> None:
    for status, stage, holder in _CASES:
        cur = _current(status)
        assert cur.get("stage") == stage, f"{status}: 当前段应 {stage}，got {cur.get('stage')}"
        assert cur.get("holder") == holder, f"{status}: holder 应 {holder!r}，got {cur.get('holder')!r}"


def test_supplementing_is_delivery_stage_not_review() -> None:
    """根治回归：补录态=已审批·下发基层补录 → 脊柱画成交付段（前 3 段全 done），绝不退回审核中·受理台。"""
    svc = RequestService.__new__(RequestService)
    rows = svc.status_timeline(dict(_REQ, status="supplementing"), None, perspective="applicant")
    assert [r["status"] for r in rows] == ["done", "done", "done", "current"]
    assert rows[3]["stage"] == "交付"
    assert rows[3]["label"] == "补录中"
    assert rows[3]["holder"] == "镇街/村社区填报人（补录）"


def test_terminal_states_no_current_no_holder() -> None:
    """终态（已授权/已汇总）全 done、无当前段、无 holder。"""
    for status in ("granted", "completed"):
        assert _current(status) == {}, f"{status} 应无当前段"


def test_national_channel_dept_approved_holder_is_busiaudit_escalate() -> None:
    """国家通道 dept_approved = 待业务运营员转报，不是部门管理员审核。"""
    svc = RequestService.__new__(RequestService)
    rows = svc.status_timeline(
        {"id": "R", "status": "dept_approved", "channelClass": "national"},
        None,
        perspective="applicant",
    )
    cur = next(s for s in rows if s["status"] == "current")
    assert cur["holder"] == "业务运营员（待转报）"


def test_provider_name_absent_falls_back_no_fabrication() -> None:
    """部门审核 holder 缺提供方局名时退「部门管理员（部门审核）」，不捏造局名。"""
    svc = RequestService.__new__(RequestService)
    rows = svc.status_timeline({"id": "R", "status": "dept_approved"}, None, perspective="applicant")
    cur = next(s for s in rows if s["status"] == "current")
    assert cur["holder"] == "部门管理员（部门审核）"


def test_approved_with_pending_delivery_shows_supplement_holder() -> None:
    """approved/in_delivery + 真补录态 delivery → 同补录 holder（合一分支的另一半，防 supplementing 单点回归）。"""
    svc = RequestService.__new__(RequestService)
    for st in ("approved", "in_delivery"):
        rows = svc.status_timeline({"id": "R", "status": st}, {"status": "pending"}, perspective="applicant")
        cur = next(s for s in rows if s["status"] == "current")
        assert cur["holder"] == "镇街/村社区填报人（补录）", f"{st}+pending delivery"
