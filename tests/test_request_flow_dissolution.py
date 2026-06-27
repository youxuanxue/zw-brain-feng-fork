"""IA 重构守卫：「办申请」(request-flow) 独立导航解体 —— 我的申请/我的授权并入领数据
(P4Delivery)、删导航与列表页、子路由保留为深链可达。

本仓前端无 vitest 体系（tests/e2e/*.spec.ts 是 Playwright，前端逻辑的「单元」守卫一律
以 Python 解析 TS/Vue 源文本实现，见 tests/test_page_access.py）。故本守卫沿用同一惯例：
不实跑浏览器，只断言源文件的结构契约——

  1) productShellNav.ts 不再列 request-flow 导航项；activeShellKey('/request-flow/*')
     回落 delivery-exchange；领数据 navDesc 反映吸收后的内容。
  2) pageAccess.ts ROUTE_ROLE_OVERRIDES 给四条 orphaned 子路由声明正确角色集
     （reviewer 详情含 BUSIAUDIT；申请详情=操作员/管理员；异议/供需=消费方三角色）。
  3) router/index.ts 把 /request-flow 列表根改为 redirect 到 /delivery-exchange，
     保留各子路由记录，删 P3RequestFlow import。
  4) P3RequestFlow.vue 已删；P4Delivery.vue 承接「我的申请」「我的授权」两段 + 深链
     #/request-flow/request/:id，且 applicant-only（无权 = 不渲染）。
  5) 全站无 LIST-ROOT 裸 #/request-flow 深链（子路径深链保留）。

路由角色判定复用 test_page_access.py 的镜像（同一真值源），避免双份口径漂移。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_page_access import _is_route_allowed

pytestmark = pytest.mark.no_db

_ROOT = Path(__file__).resolve().parents[1]
_WEB_SRC = _ROOT / "zw-brain-web" / "src"


def _read(rel: str) -> str:
    return (_WEB_SRC / rel).read_text(encoding="utf-8")


# ── 1) 导航项删除 + activeShellKey 回落 ────────────────────────────────────────

def test_product_shell_nav_no_longer_lists_request_flow() -> None:
    src = _read("config/productShellNav.ts")
    assert "key: 'request-flow'" not in src, (
        "PRODUCT_SHELL_NAV 必须删除 request-flow 导航项（「办申请」独立导航解体）"
    )
    assert "to: '/request-flow'" not in src, "request-flow 顶层导航 to 必须移除"
    # 领数据导航项仍在。
    assert "key: 'delivery-exchange'" in src, "delivery-exchange 导航项须保留"


def test_active_shell_key_request_flow_resolves_to_delivery() -> None:
    src = _read("config/productShellNav.ts")
    # /request-flow/* 子路由深链须落 delivery-exchange shell（高亮/授权归属领数据）。
    m = re.search(
        r"if \(p\.startsWith\('/request-flow'\)\) return '([^']+)';", src
    )
    assert m, "activeShellKey 必须显式处理 /request-flow 前缀"
    assert m.group(1) == "delivery-exchange", (
        f"/request-flow/* 须回落 delivery-exchange shell，实得 {m.group(1)!r}"
    )


def test_delivery_nav_desc_reflects_absorbed_content() -> None:
    src = _read("config/productShellNav.ts")
    # navDesc 应反映吸收后的「申请进度 / 凭据领取 / 交付回执」内容（业务中文、无工程黑话）。
    m = re.search(
        r"key: 'delivery-exchange'[\s\S]*?navDesc: '([^']+)'", src
    )
    assert m, "未找到 delivery-exchange navDesc"
    desc = m.group(1)
    assert "申请进度" in desc, (
        f"领数据 navDesc 须反映吸收的「我的申请」内容（申请进度），实得 {desc!r}"
    )


# ── 2) ROUTE_ROLE_OVERRIDES 角色正确（复用单一真值镜像判定）────────────────────

def test_orphaned_subroutes_keep_correct_roles() -> None:
    # /request-flow/review：reviewer 决策详情 —— BUSIAUDIT 受理、MANAGER 审核。
    assert _is_route_allowed("/request-flow/review/abc", "ROLE_BUSIAUDIT")
    assert _is_route_allowed("/request-flow/review/abc", "ROLE_ORGAN_MANAGER")
    # 申请人（操作员）不能进 reviewer 决策详情。
    assert not _is_route_allowed("/request-flow/review/abc", "ROLE_ORGAN_OPERATER")

    # /request-flow/request：申请人详情 + 补录；业务运营员在同一详情面处理授权收回/暂停。
    assert _is_route_allowed("/request-flow/request/abc", "ROLE_ORGAN_OPERATER")
    assert _is_route_allowed("/request-flow/request/abc", "ROLE_ORGAN_MANAGER")
    assert _is_route_allowed("/request-flow/request/abc", "ROLE_BUSIAUDIT")

    # /request-flow/objection（含 /:id）：消费方「我的异议」—— 操作员/管理员/业务运营员。
    for sub in ("/request-flow/objection", "/request-flow/objection/xyz"):
        assert _is_route_allowed(sub, "ROLE_ORGAN_OPERATER")
        assert _is_route_allowed(sub, "ROLE_ORGAN_MANAGER")
        assert _is_route_allowed(sub, "ROLE_BUSIAUDIT")
        assert not _is_route_allowed(sub, "ROLE_SECURITY_AUDIT")
        assert not _is_route_allowed(sub, "ROLE_SYSTEM")

    # /request-flow/objection/new：发起异议是申请人动作，业务运营员只跟踪/归档，不展示发起面。
    assert _is_route_allowed("/request-flow/objection/new", "ROLE_ORGAN_OPERATER")
    assert _is_route_allowed("/request-flow/objection/new", "ROLE_ORGAN_MANAGER")
    assert not _is_route_allowed("/request-flow/objection/new", "ROLE_BUSIAUDIT")

    # /request-flow/supply-demand：消费方供需对接 —— 消费方三角色。
    assert _is_route_allowed("/request-flow/supply-demand", "ROLE_ORGAN_OPERATER")
    assert _is_route_allowed("/request-flow/supply-demand", "ROLE_ORGAN_MANAGER")
    assert _is_route_allowed("/request-flow/supply-demand", "ROLE_BUSIAUDIT")
    assert not _is_route_allowed("/request-flow/supply-demand", "ROLE_SYSTEM")


def test_subroutes_not_silently_delivery_shell_gated() -> None:
    """关键回归：删导航后 /request-flow/* 默认会回落 delivery shell [OPERATER,MANAGER]，
    会错误地把 reviewer (BUSIAUDIT) 挡在审核详情外。override 必须纠正这一点。"""
    # 若 override 缺失，BUSIAUDIT 会被 delivery shell 拒绝 → 此断言守住 override 生效。
    assert _is_route_allowed("/request-flow/review/abc", "ROLE_BUSIAUDIT"), (
        "ROUTE_ROLE_OVERRIDES 缺 /request-flow/review → reviewer 被 delivery shell 误拒"
    )


# ── 3) router 列表根重定向 + 子路由保留 + 删 import ───────────────────────────

def test_router_list_root_redirects_and_keeps_subroutes() -> None:
    src = _read("router/index.ts")
    # P3RequestFlow import 已删。
    assert "P3RequestFlow" not in src, "router 必须删除 P3RequestFlow import（列表页已删）"
    # /request-flow 列表根 = redirect 到 /delivery-exchange（不再挂组件）。
    assert re.search(
        r"path: '/request-flow',\s*redirect: '/delivery-exchange'", src
    ), "/request-flow 必须改为 redirect 到 /delivery-exchange"
    # 各子路由记录保留（指向原组件）。
    for sub, comp in [
        ("/request-flow/request/:id", "P3RequestDetail"),
        ("/request-flow/review/:id", "P3ReviewDetail"),
        ("/request-flow/objection", "P3ObjectionInbox"),
        ("/request-flow/objection/new", "P3ObjectionNew"),
        ("/request-flow/objection/:id", "P3ObjectionDetail"),
        ("/request-flow/supply-demand", "P3SupplyDemand"),
    ]:
        assert f"path: '{sub}'" in src, f"子路由 {sub} 必须保留"
        assert comp in src, f"子路由组件 {comp} 的 import/挂载须保留"


# ── 4) 列表页删除 + P4Delivery 承接我的申请/我的授权 ──────────────────────────

def test_p3_request_flow_page_deleted() -> None:
    assert not (_WEB_SRC / "pages" / "P3RequestFlow.vue").exists(), (
        "P3RequestFlow.vue（被解体的列表页）必须删除"
    )
    # 行为断言（非仅文件存在，守 test-philosophy §3）：解体后 router 不得残留对该组件的
    # import/挂载——文件删了但 router 仍引用会 build 失败/留死引用，故一并验路由侧已收口。
    assert "P3RequestFlow" not in _read("router/index.ts"), (
        "router 不得残留 P3RequestFlow import/挂载（列表页已解体）"
    )


def test_p4_delivery_rehomes_mine_and_grants_sections() -> None:
    src = _read("pages/P4Delivery.vue")
    # 我的申请 / 我的授权 两段在场。
    assert "我的申请" in src and "我的授权" in src, (
        "P4Delivery 必须承接「我的申请」「我的授权」两段（从 P3RequestFlow 迁入）"
    )
    # 复用 projection（不新造后端调用）。
    assert "myRequests" in src and "myGrants" in src, (
        "P4Delivery 须复用 roleProjection.myRequests / myGrants（不新造后端调用）"
    )
    # 我的申请 / 我的授权 段深链到保留的申请详情子路由。
    assert "#/request-flow/request/${it.id}" in src, (
        "P4Delivery「我的申请/我的授权」须深链到 #/request-flow/request/:id（保留子路由）"
    )
    # 保留原交付任务内容。
    assert "useDeliveryTasks" in src and "交付任务" in src, (
        "P4Delivery 须保留原交付任务内容"
    )
    # 受理/审核 tab 不得迁入（该工作迁工作台）。
    assert "p4-view-todo" not in src and "待我办理" not in src, (
        "受理/审核（待我办理）不得迁入 P4Delivery —— 该工作迁工作台"
    )


def test_p4_delivery_mine_grants_are_applicant_only() -> None:
    """无权 = 不可见：我的申请 / 我的授权 段对非申请人不渲染（v-if 门控）。"""
    delivery_src = _read("pages/P4Delivery.vue")
    tabs_src = _read("components/DeliveryEntryTabs.vue")
    assert "isApplicantRole" in delivery_src, "P4Delivery 须有 isApplicantRole 申请人身份判定"
    assert "showApplicantTabs" in tabs_src, "DeliveryEntryTabs 须接收 showApplicantTabs 门控"
    assert "showApplicantTabs: null" in tabs_src or "showApplicantTabs:null" in tabs_src.replace(" ", ""), (
        "Boolean prop 省略时 Vue 默认为 false；须 null 默认 + ?? true 才能让 P3 页自决申请人 tab"
    )
    assert "applicantEntries" in tabs_src or "我的申请" in tabs_src, (
        "「我的申请」tab 须经 showApplicantTabs / applicantEntries 门控（无权不渲染）"
    )
    assert re.search(r'v-if="isApplicantRole"[\s\S]*?data-testid="p4-pane-mine"', delivery_src), (
        "「我的申请」pane 须 v-if=\"isApplicantRole\""
    )


# ── 5) 全站无 LIST-ROOT 裸深链 ────────────────────────────────────────────────

def test_no_list_root_request_flow_deeplinks_remain() -> None:
    """LIST-ROOT 裸 #/request-flow（无后续路径段）深链必须改写到 #/delivery-exchange；
    子路径深链 (#/request-flow/review/:id 等) 保留。"""
    # 裸 #/request-flow 后紧跟引号/反引号/行尾/空白（即无 / 后续段）= 列表根深链。
    bad = re.compile(r"#/request-flow(?![/\w])")
    hits: list[str] = []
    for path in sorted(_WEB_SRC.rglob("*")):
        if path.suffix not in {".vue", ".ts"}:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if bad.search(line):
                hits.append(f"{path.relative_to(_WEB_SRC)}:{i}: {line.strip()[:90]}")
    assert not hits, (
        "仍存在 LIST-ROOT 裸 #/request-flow 深链（列表页已删，须改写到 #/delivery-exchange）：\n"
        + "\n".join(hits)
    )
