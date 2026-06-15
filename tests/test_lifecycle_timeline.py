"""J2 供数脊柱 + 异议脊柱 timeline 逐态 (当前段, holder) 回归锁（仿 J1 #280）。

把目录/资源生命周期与异议办理 9 态机的当前段 + holder 钉死：状态→当前段→holder
单调现算、holder 只挂当前段、缺省诚实留空绝不捏造、支线态（驳回/退役）不渲染 stepper。
纯函数级，不依赖 DB。
"""

from zw_brain.domain.lifecycle_timeline import (
    catalog_lifecycle_timeline,
    lifecycle_sideline_note,
    objection_sideline_note,
    objection_timeline,
    resource_lifecycle_timeline,
)


def _current(steps: list[dict]) -> dict:
    return next((s for s in steps if s["status"] == "current"), {})


# ── 目录生命周期（草稿→部门审核→平台审核→待发布→已发布）─────────────────────
_CATALOG_CASES = [
    # (status, 当前段, holder)
    ("draft", "草稿", "部门操作员（编制）"),
    ("pending_review", "部门审核", "部门管理员（部门审核）"),
    ("pending_platform_review", "平台审核", "业务运营员（平台审核）"),
    ("approved_pending_publish", "待发布", "业务运营员（发布）"),
    ("active", "已发布", ""),  # 终态：当前段=已发布，holder 诚实留空
]


def test_catalog_timeline_holder_per_state() -> None:
    for status, stage, holder in _CATALOG_CASES:
        cur = _current(catalog_lifecycle_timeline(status))
        assert cur.get("stage") == stage, f"{status}: 当前段应 {stage}，got {cur.get('stage')}"
        assert cur.get("holder") == holder, f"{status}: holder 应 {holder!r}，got {cur.get('holder')!r}"


def test_catalog_timeline_is_monotonic() -> None:
    """平台审核态：前两段 done、当前段 current、后两段 pending（单调）。"""
    rows = catalog_lifecycle_timeline("pending_platform_review")
    assert [r["status"] for r in rows] == ["done", "done", "current", "pending", "pending"]


def test_catalog_sideline_states_no_stepper_but_noted() -> None:
    """驳回/退役 = 支线终态：无 stepper（空列表），由 lifecycle note 诚实标注。"""
    for status in ("rejected", "retired", "suspended"):
        assert catalog_lifecycle_timeline(status) == [], f"{status} 不应渲染 stepper"
        assert lifecycle_sideline_note(status), f"{status} 应有中文标注"
    # 非支线（在途/终态 active）不给 note
    assert lifecycle_sideline_note("active") == ""
    assert lifecycle_sideline_note("draft") == ""


def test_catalog_unknown_status_no_stepper() -> None:
    assert catalog_lifecycle_timeline("legacy_under_review") == []
    assert catalog_lifecycle_timeline("") == []
    assert catalog_lifecycle_timeline(None) == []


# ── 资源生命周期（草稿→挂接审核→待发布→已发布，无平台审核档）──────────────────
_RESOURCE_CASES = [
    ("draft", "草稿", "部门操作员（挂接）"),
    ("pending_review", "挂接审核", "部门管理员（挂接审核）"),
    ("approved_pending_publish", "待发布", "业务运营员（发布）"),
    ("active", "已发布", ""),
]


def test_resource_timeline_holder_per_state() -> None:
    for status, stage, holder in _RESOURCE_CASES:
        cur = _current(resource_lifecycle_timeline(status))
        assert cur.get("stage") == stage, f"{status}: 当前段应 {stage}，got {cur.get('stage')}"
        assert cur.get("holder") == holder, f"{status}: holder 应 {holder!r}，got {cur.get('holder')!r}"


def test_resource_timeline_has_four_stages() -> None:
    """资源脊柱 4 段（无平台审核档，区别于目录 5 段）。"""
    rows = resource_lifecycle_timeline("pending_review")
    assert [r["stage"] for r in rows] == ["草稿", "挂接审核", "待发布", "已发布"]
    assert [r["status"] for r in rows] == ["done", "current", "pending", "pending"]


# ── 异议线（提交→受理→核查→办结→归档；核查段两态分流）────────────────────────
_OBJECTION_CASES = [
    # (status, 当前段, holder)
    ("submitted", "提交", "业务运营员（受理）"),
    ("accepted", "受理", "业务运营员（核查）"),
    ("platform_investigating", "核查", "业务运营员（核查）"),
    ("provider_investigating", "核查", "部门管理员（部门核查）"),
    ("resolved", "办结", "申请方（确认/评价）"),
    ("closed", "归档", ""),  # 终态
]


def test_objection_timeline_holder_per_state() -> None:
    for status, stage, holder in _OBJECTION_CASES:
        cur = _current(objection_timeline(status))
        assert cur.get("stage") == stage, f"{status}: 当前段应 {stage}，got {cur.get('stage')}"
        assert cur.get("holder") == holder, f"{status}: holder 应 {holder!r}，got {cur.get('holder')!r}"


def test_objection_investigating_split_label() -> None:
    """核查段两态分流：平台核查 vs 部门核查 当前段标签不同（同段、holder 不同）。"""
    plat = _current(objection_timeline("platform_investigating"))
    dept = _current(objection_timeline("provider_investigating"))
    assert plat["stage"] == dept["stage"] == "核查"
    assert plat["label"] != dept["label"]
    assert plat["holder"] != dept["holder"]


def test_objection_rejected_no_stepper_but_noted() -> None:
    """驳回 = 支线终态：无 stepper，给中文标注；其余态不给 note。"""
    assert objection_timeline("rejected") == []
    assert objection_sideline_note("rejected") == "已驳回"
    assert objection_sideline_note("submitted") == ""
    assert objection_sideline_note("closed") == ""


def test_objection_monotonic_done_current_pending() -> None:
    rows = objection_timeline("resolved")
    assert [r["status"] for r in rows] == ["done", "done", "done", "current", "pending"]
    assert rows[3]["stage"] == "办结"
