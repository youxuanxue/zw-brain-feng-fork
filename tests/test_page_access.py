"""WebUI 路由岗位门禁：与 zw-brain-web/src/lib/pageAccess.ts 语义一致。

两级权限：
  1) shell 级 — 与 productShellNav.ts PRODUCT_SHELL_NAV.roles 一致。
  2) 子路由级 — 与 pageAccess.ts ROUTE_ROLE_OVERRIDES 一致，比 shell 更严格。
"""

from __future__ import annotations

# 与 productShellNav.ts PRODUCT_SHELL_NAV 同步
_SHELL_ROLES: dict[str, frozenset[str]] = {
    "workbench": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
            "ROLE_SYSTEM",
        }
    ),
    # D55/P17：安全审计员非数据使用方，退出找数据（permission-matrix-0610 复审清掉镜像漂移；
    # 本镜像由 test_shell_roles_mirror_matches_ts 机械守卫与 TS 真值 set-equal）。
    "discovery": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
        }
    ),
    # D55/P21·P7：业务运营员（受理岗）在 request-flow shell 内办受理 + 决策A 收回/暂停
    # （与 productShellNav.ts request-flow.roles 一致，含 BUSIAUDIT）。
    "request-flow": frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}),
    # D55/P13 领数据回归操作员+管理员（反转 F1）+ P18 审计员退出 + D53⑥ 运营员无交付场景。
    "delivery-exchange": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
        }
    ),
    # provider shell 含 OPERATER（roles §66 / J2 §166 在线编制属操作员职责）
    "provider": frozenset(
        {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}
    ),
    # 查审计拆分（D55/P8·P9，Wave1-S3）：审计日志面收窄到业务运营员 + 安全审计员。
    # 部门管理员退审计日志（P9）、平台运维员退审计日志（P8）→ 二者不在 compliance-ops shell。
    "compliance-ops": frozenset(
        {
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
        }
    ),
    # 服务调用监控（D55/P8 拆分 → D57⑥ 收窄）：仅平台运维员 + 业务运营员（v5 服务调用日志口径）。
    # 部门管理员、安全审计员退出全局监控；管理员自家资源调用留 P4 凭据门内。
    "service-ops": frozenset(
        {
            "ROLE_BUSIAUDIT",
            "ROLE_SYSTEM",
        }
    ),
    # zones-pack（专题包）shell 退出本期（D55/P6）：路由下线，不再有 shell 角色门。
    # D55/P2：外部系统收归平台运维员（业务运营员退出）。
    "integration-admin": frozenset({"ROLE_SYSTEM"}),
    # D55/P3 反转 D49：流程表单配置 = 平台级系统配置 = 平台运维员独有。
    "engines": frozenset({"ROLE_SYSTEM"}),
    # D55/P4：身份治理收归平台运维员。
    "iam-governance": frozenset({"ROLE_SYSTEM"}),
}

# 与 pageAccess.ts ROUTE_ROLE_OVERRIDES 同步（顺序敏感，长前缀优先）。
# 第三列 redirectIfDenied 用于 fallback：拒绝当前 role 时优先跳的"业务对位下一站"。
_ROUTE_ROLE_OVERRIDES: list[tuple[str, frozenset[str], str | None]] = [
    (
        "/provider/wizard/inline-catalog",
        frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"}),
        "/provider/inbox/catalog-review",
    ),
    (
        "/provider/inbox/catalog-review",
        frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}),
        "/provider/wizard/inline-catalog",
    ),
    ("/provider/wizard/reverse-catalog", frozenset({"ROLE_ORGAN_MANAGER", "ROLE_ORGAN_OPERATER"}), None),
    # G3：资源挂接向导 / 代理服务注册向导 = 部门操作员 + 部门管理员（供数维护 / API 注册），业务运营员退出。
    ("/provider/wizard/hookup-submit", frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"}), None),
    ("/provider/wizard/api-service", frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"}), None),
    ("/provider/inbox/field-decision", frozenset({"ROLE_BUSIAUDIT"}), None),
    # G1：挂接审核照 v5「资源挂接审核 = 部门管理员」校正（撤回 R-007 交叉审）。
    ("/provider/inbox/hookup-review", frozenset({"ROLE_ORGAN_MANAGER"}), None),
    # G6：异议响应 = 部门管理员 + 业务运营员（v5「异议核查」），翻转 wave1.5 P20 的 MANAGER-only 锁定。
    ("/provider/inbox/objection", frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}), None),
    # C5（D50）国家扩展要素编制（角色门；flag 门在前端 hub/页内另把守）。
    ("/provider/national-ext-elem", frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}), None),
]


def _active_shell_key(path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    if p.startswith("/discovery"):
        return "discovery"
    if p.startswith("/request-flow"):
        return "request-flow"
    if p.startswith("/delivery-exchange"):
        return "delivery-exchange"
    if p.startswith("/provider"):
        return "provider"
    if p.startswith("/compliance-ops"):
        return "compliance-ops"
    if p.startswith("/service-ops"):
        return "service-ops"
    # /zones-pack 专题包路由退出本期（D55/P6）：不再映射 shell key。
    # 身份治理 / 流程表单独立导航键须在 /integration-admin 前缀之前命中（与 TS activeShellKey 一致）。
    if p.startswith("/integration-admin/iam-governance"):
        return "iam-governance"
    if p.startswith("/integration-admin/engines"):
        return "engines"
    if p.startswith("/integration-admin"):
        return "integration-admin"
    return "workbench"


def _match_override(
    path: str,
) -> tuple[frozenset[str], str | None] | None:
    for prefix, roles, redirect in _ROUTE_ROLE_OVERRIDES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return roles, redirect
    return None


def _is_route_allowed(path: str, role: str) -> bool:
    override = _match_override(path)
    if override is not None:
        return role in override[0]
    key = _active_shell_key(path)
    return role in _SHELL_ROLES.get(key, frozenset())


def _default_route_for_role(role: str, from_path: str | None = None) -> str:
    """与 pageAccess.ts defaultRouteForRole 对齐。"""
    if from_path:
        override = _match_override(from_path)
        if override is not None:
            _, redirect = override
            if redirect and _is_route_allowed(redirect, role):
                return redirect
        shell_key = _active_shell_key(from_path)
        shell_roles = _SHELL_ROLES.get(shell_key, frozenset())
        # 假设 shell 顶层路由是 "/" + key（productShellNav 中所有 to 都是这个形式）
        shell_top = f"/{shell_key}"
        if role in shell_roles and from_path != shell_top:
            return shell_top
    # 否则回落到 role 第一个可见 shell（按 PRODUCT_SHELL_NAV 顺序）
    for sk in ("workbench", "discovery", "request-flow", "delivery-exchange",
               "provider", "compliance-ops", "service-ops", "integration-admin",
               "engines", "iam-governance"):
        if role in _SHELL_ROLES.get(sk, frozenset()):
            return f"/{sk}"
    return "/workbench"


def test_operater_cannot_access_integration_admin() -> None:
    assert not _is_route_allowed("/integration-admin", "ROLE_ORGAN_OPERATER")
    assert not _is_route_allowed("/integration-admin/engines", "ROLE_ORGAN_OPERATER")


def test_system_can_access_integration_admin() -> None:
    assert _is_route_allowed("/integration-admin", "ROLE_SYSTEM")


def test_operater_can_access_workbench() -> None:
    assert _is_route_allowed("/workbench", "ROLE_ORGAN_OPERATER")


def test_operater_can_access_provider_shell_and_inline_wizard() -> None:
    # provider shell 顶层对 OPERATER 开放（在线编制入口）
    assert _is_route_allowed("/provider", "ROLE_ORGAN_OPERATER")
    # 在线编制 wizard 仅 OPERATER
    assert _is_route_allowed(
        "/provider/wizard/inline-catalog", "ROLE_ORGAN_OPERATER"
    )


def test_manager_can_access_inline_catalog_wizard() -> None:
    # D55/P11：管理员也可直接进在线编制（不再被踢到 inbox）
    assert _is_route_allowed(
        "/provider/wizard/inline-catalog", "ROLE_ORGAN_MANAGER"
    )
    # BUSIAUDIT 仍不可进（只审不编）
    assert not _is_route_allowed(
        "/provider/wizard/inline-catalog", "ROLE_BUSIAUDIT"
    )


def test_catalog_review_inbox_dual_layer() -> None:
    # 部门审 + 平台审两层 reviewer 都能进
    assert _is_route_allowed(
        "/provider/inbox/catalog-review", "ROLE_ORGAN_MANAGER"
    )
    assert _is_route_allowed("/provider/inbox/catalog-review", "ROLE_BUSIAUDIT")
    # OPERATER 不能进（自己提交后切角色应被踢走）
    assert not _is_route_allowed(
        "/provider/inbox/catalog-review", "ROLE_ORGAN_OPERATER"
    )


def test_hookup_review_only_manager() -> None:
    # G1（D55 查缺补漏）：挂接审核照 v5「资源挂接审核 = 部门管理员」校正（撤回 R-007 交叉审）。
    assert _is_route_allowed("/provider/inbox/hookup-review", "ROLE_ORGAN_MANAGER")
    # 业务运营员退出挂接审核（其职责是发布 / 受理，不是审挂接）。
    assert not _is_route_allowed(
        "/provider/inbox/hookup-review", "ROLE_BUSIAUDIT"
    )


def test_supply_wizards_operater_and_manager_only() -> None:
    # G3：资源挂接向导 / 代理服务注册向导 = 部门操作员 + 部门管理员；业务运营员退出供数注册。
    for route in ("/provider/wizard/hookup-submit", "/provider/wizard/api-service"):
        assert _is_route_allowed(route, "ROLE_ORGAN_OPERATER")
        assert _is_route_allowed(route, "ROLE_ORGAN_MANAGER")
        assert not _is_route_allowed(route, "ROLE_BUSIAUDIT")


def test_field_decision_only_busiaudit() -> None:
    assert _is_route_allowed(
        "/provider/inbox/field-decision/abc", "ROLE_BUSIAUDIT"
    )
    assert not _is_route_allowed(
        "/provider/inbox/field-decision/abc", "ROLE_ORGAN_OPERATER"
    )


def test_provider_inbox_objection_manager_and_busiaudit() -> None:
    # G6（D55 查缺补漏）：异议响应 = 部门管理员 + 业务运营员（v5「异议核查」）。
    # 翻转 wave1.5 P20 故意锁定的 MANAGER-only 断言 —— 口径校准时它本就是为此存在。
    assert _is_route_allowed(
        "/provider/inbox/objection/xyz", "ROLE_ORGAN_MANAGER"
    )
    assert _is_route_allowed(
        "/provider/inbox/objection/xyz", "ROLE_BUSIAUDIT"
    )
    # 部门操作员仍不可进（不办异议）。
    assert not _is_route_allowed(
        "/provider/inbox/objection/xyz", "ROLE_ORGAN_OPERATER"
    )


def test_national_ext_elem_manager_and_busiaudit_only() -> None:
    # C5：部门管理员 + 业务运营员可进国家扩展要素编制；操作员不可见。
    assert _is_route_allowed("/provider/national-ext-elem", "ROLE_ORGAN_MANAGER")
    assert _is_route_allowed("/provider/national-ext-elem", "ROLE_BUSIAUDIT")
    assert not _is_route_allowed("/provider/national-ext-elem", "ROLE_ORGAN_OPERATER")


def test_reverse_catalog_wizard_manager_and_operater() -> None:
    # D55/P14：操作员 + 管理员均可进反向编目向导
    assert _is_route_allowed(
        "/provider/wizard/reverse-catalog", "ROLE_ORGAN_MANAGER"
    )
    assert _is_route_allowed(
        "/provider/wizard/reverse-catalog", "ROLE_ORGAN_OPERATER"
    )
    # BUSIAUDIT 只审核，不进 wizard
    assert not _is_route_allowed(
        "/provider/wizard/reverse-catalog", "ROLE_BUSIAUDIT"
    )


# ---- defaultRouteForRole (业务对位 redirect) ----

def test_default_redirect_from_inline_wizard_to_review_inbox() -> None:
    """OPERATER 在 wizard 上提交后切到 MANAGER/BUSIAUDIT → 直接落到目录审核收件箱。"""
    assert (
        _default_route_for_role(
            "ROLE_ORGAN_MANAGER", "/provider/wizard/inline-catalog"
        )
        == "/provider/inbox/catalog-review"
    )
    assert (
        _default_route_for_role(
            "ROLE_BUSIAUDIT", "/provider/wizard/inline-catalog"
        )
        == "/provider/inbox/catalog-review"
    )


def test_default_redirect_from_review_inbox_to_wizard() -> None:
    """reviewer 在 inbox 切到 OPERATER → 落到在线编制 wizard。"""
    assert (
        _default_route_for_role(
            "ROLE_ORGAN_OPERATER", "/provider/inbox/catalog-review"
        )
        == "/provider/wizard/inline-catalog"
    )


def test_default_fallback_to_shell_top() -> None:
    """无 override redirect 时回 shell 顶层，避免落到 /workbench。"""
    # reverse-catalog wizard 没有 redirectIfDenied，但 provider shell 对 OPERATER 开放
    assert (
        _default_route_for_role(
            "ROLE_ORGAN_OPERATER", "/provider/wizard/reverse-catalog"
        )
        == "/provider"
    )


def test_default_fallback_to_first_visible_shell_when_no_context() -> None:
    """无 fromPath → 回 role 第一个可见 shell。"""
    assert (
        _default_route_for_role("ROLE_ORGAN_OPERATER") == "/workbench"
    )


def test_auth_fetch_has_default_timeout() -> None:
    """authFetch 必须给所有 fetch 套 AbortSignal.timeout，否则后端无响应时 UI 永远停在
    "正在加载……"。

    背景：J2-5 用户在 B1.2 接入扩展中心见 "正在加载……" 一直转圈。composable
    已有 `try/catch + fixture` 回退，但 fetch 永不 resolve 时 catch 触发不了
    （非 2xx 抛错 / JS 异常都能 catch，唯独网络层僵尸连接需要 abort）。
    单点修在 authFetch（chokepoint），17+ composable 自然继承上限：
      1) 必须声明 DEFAULT_FETCH_TIMEOUT_MS 常量；
      2) 必须用 AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS) 注入；
      3) 必须用 AbortSignal.any 合并 caller 自带 signal，避免覆盖。
    新增 escape hatch（如 long-poll/SSE）应通过 init.signal=null 显式表达，
    本测试不限制；只守住默认上限存在。
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "zw-brain-web" / "src" / "composables" / "useAuth.ts"
    ).read_text(encoding="utf-8")
    assert "DEFAULT_FETCH_TIMEOUT_MS" in src, (
        "useAuth.ts 必须声明 DEFAULT_FETCH_TIMEOUT_MS 常量作为所有 fetch 上限"
    )
    assert "AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS)" in src, (
        "authFetch 必须用 AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS) 注入超时"
    )
    assert "AbortSignal.any(" in src, (
        "authFetch 必须用 AbortSignal.any 合并 caller signal + timeout signal，"
        "禁止直接覆盖 init.signal"
    )


def test_page_focus_header_filters_links_by_role() -> None:
    """PageFocusHeader.vue 必须按当前 role 过滤 sub-nav links。

    背景：J2-4 业务运营员看到「在线编制 / 反向编目」等无权入口，点击只能弹
    toast。共性根因是页面右上角 sub-nav 链是静态渲染，未走 role gate。
    chokepoint 已抽到 pageAccess.filterByRouteAccess（同样供 P5Provider 待办卡用），
    本测试守住 PageFocusHeader 必须复用该 chokepoint：
      1) 必须 import filterByRouteAccess；
      2) 必须基于 visibleLinks（计算属性）而不是原始 links 渲染 <a>；
      3) 模板 v-for 必须基于 visibleLinks。
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "zw-brain-web" / "src" / "components" / "PageFocusHeader.vue"
    ).read_text(encoding="utf-8")
    assert "filterByRouteAccess" in src, (
        "PageFocusHeader.vue 必须 import pageAccess.filterByRouteAccess 复用 chokepoint"
    )
    assert "visibleLinks" in src, (
        "PageFocusHeader.vue 必须用 visibleLinks 计算属性渲染 <a>，不能直接遍历 links"
    )
    assert 'in visibleLinks"' in src, (
        "PageFocusHeader.vue 模板 v-for 必须基于 visibleLinks，否则 sub-nav 不会按 role 过滤"
    )


def test_p5_provider_filters_stat_cards_and_publish_action() -> None:
    """P5Provider.vue 必须按 role 过滤 inbox 计数卡 + 按 action 闸 publish 按钮。

    背景：J2-7 OPERATER 看到「字段审核/挂接审核/供需对接/异议响应」4 张待办卡 +
    3 个「发布「xxx」」按钮全亮（点击只弹 toast）。前 3 张卡 href 指向无权 inbox 路由；
    发布按钮走 catalog.entry.publish action（后端 policy.py 限 MANAGER+BUSIAUDIT）。
    chokepoint：
      1) 待办卡 → pageAccess.filterByRouteAccess（route-based，同 PageFocusHeader）；
      2) 发布按钮 → pageAccess.canPerformAction('catalog.entry.publish', role)
         （action-based，与后端 policy 对齐）。
    新增类似页面 CTA 应统一走这两个 chokepoint，禁止在 page 内自己实现 role 比对。
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "zw-brain-web" / "src" / "pages" / "P5Provider.vue"
    ).read_text(encoding="utf-8")
    assert "filterByRouteAccess" in src and "canPerformAction" in src, (
        "P5Provider.vue 必须 import filterByRouteAccess + canPerformAction 两个 chokepoint"
    )
    assert "visibleStatCards" in src, (
        "P5Provider.vue 必须用 visibleStatCards 计算属性过滤待办卡"
    )
    assert "canPublishCatalog" in src, (
        "P5Provider.vue 必须用 canPublishCatalog 计算属性闸 publish 按钮区"
    )
    assert 'v-for="c in visibleStatCards"' in src, (
        "模板 v-for 必须基于 visibleStatCards，OPERATER 才看不到无权 inbox 卡"
    )
    assert 'v-if="source === \'live\' && canPublishCatalog"' in src, (
        "publish-section 必须 v-if 闸在 canPublishCatalog，OPERATER 才看不到发布按钮"
    )


def test_action_role_gates_aligned_with_backend_policy() -> None:
    """前端 ACTION_ROLE_GATES 中的每个 action 必须与后端 policy.PERMISSION_ROLES 一致。

    chokepoint 是 zw_brain/domain/policy.py PERMISSION_ROLES（权威源）；前端 gate 表
    只列会渲染 CTA 的子集，但每个声明的 action 都必须 set-equal 后端权限。新增 CTA
    想 gate 时直接在两侧追加，本测试会立刻拦下漂移。

    `catalog.entry.publish` 是首批：J2-7 修复时引入。
    """
    import re
    from pathlib import Path

    from zw_brain.domain import policy

    src = (
        Path(__file__).resolve().parent.parent
        / "zw-brain-web" / "src" / "lib" / "pageAccess.ts"
    ).read_text(encoding="utf-8")

    # 提取 ACTION_ROLE_GATES 字面量块（吃 Readonly<Record<...>> 嵌套泛型）
    m = re.search(r"ACTION_ROLE_GATES\b[^=]*=\s*\{([^}]+)\}", src, re.DOTALL)
    assert m, "pageAccess.ts 必须显式声明 ACTION_ROLE_GATES 表"
    body = m.group(1)
    # 每行形如 `'action.id': ['ROLE_X', 'ROLE_Y'],`
    entries: dict[str, frozenset[str]] = {}
    for line in body.splitlines():
        em = re.match(r"\s*'([^']+)'\s*:\s*\[([^\]]+)\]", line)
        if not em:
            continue
        action = em.group(1)
        roles = frozenset(re.findall(r"'([^']+)'", em.group(2)))
        entries[action] = roles
    assert entries, "ACTION_ROLE_GATES 至少应包含一条（首批 catalog.entry.publish）"

    for action, fe_roles in entries.items():
        # 后端 policy 用 `<action>.execute` 形式登记
        be_key = f"{action}.execute"
        be_roles = policy.PERMISSION_ROLES.get(be_key)
        assert be_roles is not None, (
            f"前端 ACTION_ROLE_GATES['{action}'] 在后端 policy.PERMISSION_ROLES 找不到 "
            f"'{be_key}'；若 action 名变化，请两侧同步"
        )
        assert set(fe_roles) == set(be_roles), (
            f"前端 ACTION_ROLE_GATES['{action}']={sorted(fe_roles)} 与后端 "
            f"policy.PERMISSION_ROLES['{be_key}']={sorted(be_roles)} 漂移；"
            f"权威源是后端，请同步前端"
        )


# ─────────────────────────────────────────────────────────────────────────────
# D55/P20：工作台投影深链 ↔ 路由权限对齐守卫
# 工作台所有待办/入口深链目标必须对其被投递到的角色 isRouteAllowedForRole=true，
# 否则会渲染「点了跳无权页」的死链。本守卫把投影的深链口径与 pageAccess 路由门对齐。
# ─────────────────────────────────────────────────────────────────────────────

def _href_to_path(href: str) -> str:
    """`#/foo/bar/<id>` → `/foo/bar`（去锚点 + 去末尾 <id> 占位段）。"""
    path = href[1:] if href.startswith("#") else href
    # 去掉形如 /<id> 的尾随占位（投影深链里 review/<id> 的 <id> 不影响 shell 归属）。
    return path


# 工作台投影的角色 → 深链目标集合（与 zw_brain/domain/workbench_backlog_projection.py +
# zw_brain/command/sync.py sync_request_todos 的 href 单源对齐）。
_PROJECTION_DEEPLINKS: dict[str, frozenset[str]] = {
    # 业务运营员（受理岗 + 发布/汇总积压）
    "ROLE_BUSIAUDIT": frozenset(
        {
            "/request-flow/review",        # 受理待办（sync_request_todos accept）
            "/request-flow",               # 待受理申请 backlog
            "/provider",                   # 待发布目录/资源 backlog
            "/provider/inbox/demand-match",  # 待汇总需求 backlog
            # G6（D55 查缺补漏）：异议收件箱按 v5「异议核查 = 业务运营员 + 部门管理员」开放
            # BUSIAUDIT 后深链激活，移入 must-pass（原 known-debt 锁定断言随校准删除）。
            "/provider/inbox/objection",   # 待受理异议 backlog
        }
    ),
    # 部门管理员（部门审核 + 供数侧目录审核）
    "ROLE_ORGAN_MANAGER": frozenset(
        {
            "/request-flow/review",                # 部门审核待办（dept_approved）
            "/provider/inbox/catalog-review",      # 目录待部门审 backlog（P10）
        }
    ),
    # 部门操作员（申请进度）
    "ROLE_ORGAN_OPERATER": frozenset(
        {
            "/request-flow/request",  # 申请进度跟踪 / 补录任务
        }
    ),
}


def test_workbench_projection_deeplinks_route_allowed_for_role() -> None:
    """D55/P20：工作台投影的每个深链目标必须对其投递角色路由可达（无死链）。

    注：业务运营员「待受理异议」深链 /provider/inbox/objection 现 ROUTE_ROLE_OVERRIDES=
    [ROLE_ORGAN_MANAGER]（异议受理人角色口径属 D28 GATE 既有债，见 workbench.py 注释），
    本守卫如实暴露——若该投影深链对 BUSIAUDIT 不可达则 FAIL，迫使口径校准（投影 or 路由门
    二选一），不放过死链。
    """
    failures: list[str] = []
    for role, hrefs in _PROJECTION_DEEPLINKS.items():
        for href in hrefs:
            path = _href_to_path(href)
            if not _is_route_allowed(path, role):
                failures.append(f"{role} → {path}（投影深链路由不可达，死链）")
    assert not failures, "工作台投影深链存在角色不可达的死链：\n" + "\n".join(failures)


def test_busiaudit_objection_inbox_reachable() -> None:
    """G6（D55 查缺补漏）：异议收件箱对业务运营员可达（v5 异议核查 = 业务运营员 + 部门管理员）。

    原 known-debt 锁定断言（钉死「不可达」等口径校准）已随 G6 校准翻转为正向可达守卫。
    """
    assert _is_route_allowed("/provider/inbox/objection", "ROLE_BUSIAUDIT")
    assert _is_route_allowed("/provider/inbox/objection", "ROLE_ORGAN_MANAGER")


# ─────────────────────────────────────────────────────────────────────────────
# permission-matrix-0610 守卫硬化（升级原则 §5：把本轮缺陷类机械封死）
# ─────────────────────────────────────────────────────────────────────────────

def _web_src_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "zw-brain-web" / "src"


def test_shell_roles_mirror_matches_ts() -> None:
    """本文件 _SHELL_ROLES 镜像必须与 productShellNav.ts 真值 set-equal。

    背景（permission-matrix-0610）：D55 wave1 改了 TS 真值（discovery/delivery 去审计员、
    integration-admin 收 SYSTEM、新增 engines/iam-governance 键），但本镜像漂移未跟——
    镜像比真值宽 = 守卫弱化（放过真 UI 已拒绝的角色）。本测试把「与 productShellNav.ts 同步」
    的注释承诺机械化，漂移即 FAIL。
    """
    import re

    src = (_web_src_root() / "config" / "productShellNav.ts").read_text(encoding="utf-8")
    ts_shells: dict[str, frozenset[str]] = {}
    for m in re.finditer(r"key:\s*'([^']+)'.*?roles:\s*\[([^\]]+)\]", src, re.DOTALL):
        ts_shells[m.group(1)] = frozenset(re.findall(r"'(ROLE_[A-Z_]+)'", m.group(2)))
    assert ts_shells, "productShellNav.ts 解析不到任何 shell（解析器或文件结构变了）"
    assert set(ts_shells) == set(_SHELL_ROLES), (
        f"shell 键集漂移：TS={sorted(ts_shells)} vs 镜像={sorted(_SHELL_ROLES)}"
    )
    for key, ts_roles in ts_shells.items():
        assert _SHELL_ROLES[key] == ts_roles, (
            f"_SHELL_ROLES[{key!r}]={sorted(_SHELL_ROLES[key])} 与 TS 真值 "
            f"{sorted(ts_roles)} 漂移；真值源是 productShellNav.ts，请同步镜像"
        )


def test_all_canperformaction_ids_registered() -> None:
    """src 内每个 canPerformAction('<literal>') 必须已注册进 ACTION_ROLE_GATES。

    背景（permission-matrix-0610）：canPerformAction 对未注册 action 默认放行
    （pageAccess.ts「未注册的 action 默认不拦」），ops.service.invocation.query 因此
    对操作员渲染了入口但后端 403。本测试封死「用了 gate 函数却没登记 gate」的缺陷类。
    """
    import re

    src_root = _web_src_root()
    gates_src = (src_root / "lib" / "pageAccess.ts").read_text(encoding="utf-8")
    m = re.search(r"ACTION_ROLE_GATES\b[^=]*=\s*\{(.*?)\n\};", gates_src, re.DOTALL)
    assert m, "pageAccess.ts 缺 ACTION_ROLE_GATES 表"
    registered = set(re.findall(r"'([^']+)'\s*:\s*\[", m.group(1)))

    unregistered: list[str] = []
    for path in sorted(src_root.rglob("*")):
        if path.suffix not in {".vue", ".ts"} or path.name == "pageAccess.ts":
            continue
        text = path.read_text(encoding="utf-8")
        for am in re.finditer(r"canPerformAction\(\s*'([^']+)'", text):
            if am.group(1) not in registered:
                unregistered.append(f"{path.relative_to(src_root)}: {am.group(1)}")
    assert not unregistered, (
        "以下 canPerformAction 调用的 action 未注册进 ACTION_ROLE_GATES"
        "（未注册=默认放行，会渲染无权入口）：\n" + "\n".join(unregistered)
    )


def test_no_hardcoded_role_arrays_in_pages() -> None:
    """src/pages/*.vue 禁止硬编码 ['ROLE_…'] 角色数组——角色门一律走
    pageAccess（canPerformAction/filterByRouteAccess）或 requestFlowRoles 常量。

    背景（permission-matrix-0610）：P3ObjectionDetail canClose 硬编码含安全审计员，
    与后端 objection.case.close={MANAGER,BUSIAUDIT} 漂移（D55/P22 违例）。
    """
    import re

    pages = _web_src_root() / "pages"
    hits: list[str] = []
    for path in sorted(pages.glob("*.vue")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\[\s*'ROLE_[A-Z_]+'", line):
                hits.append(f"{path.name}:{i}: {line.strip()[:100]}")
    assert not hits, (
        "pages 内发现硬编码角色数组（应走 pageAccess/requestFlowRoles chokepoint）：\n"
        + "\n".join(hits)
    )
