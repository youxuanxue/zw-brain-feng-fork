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
    "discovery": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
        }
    ),
    "request-flow": frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"}),
    "delivery-exchange": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
        }
    ),
    # provider shell 含 OPERATER（roles §66 / J2 §166 在线编制属操作员职责）
    "provider": frozenset(
        {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}
    ),
    "compliance-ops": frozenset(
        {
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
            # ROLE_SECURITY_ADMIN 随安全管理员本期退役而移除（D55/P16）。
            "ROLE_SYSTEM",
        }
    ),
    # zones-pack（专题包）shell 退出本期（D55/P6）：路由下线，不再有 shell 角色门。
    "integration-admin": frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM"}),
}

# 与 pageAccess.ts ROUTE_ROLE_OVERRIDES 同步（顺序敏感，长前缀优先）。
# 第三列 redirectIfDenied 用于 fallback：拒绝当前 role 时优先跳的"业务对位下一站"。
_ROUTE_ROLE_OVERRIDES: list[tuple[str, frozenset[str], str | None]] = [
    (
        "/provider/wizard/inline-catalog",
        frozenset({"ROLE_ORGAN_OPERATER"}),
        "/provider/inbox/catalog-review",
    ),
    (
        "/provider/inbox/catalog-review",
        frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}),
        "/provider/wizard/inline-catalog",
    ),
    ("/provider/wizard/reverse-catalog", frozenset({"ROLE_ORGAN_MANAGER"}), None),
    ("/provider/inbox/field-decision", frozenset({"ROLE_BUSIAUDIT"}), None),
    ("/provider/inbox/hookup-review", frozenset({"ROLE_BUSIAUDIT"}), None),
    ("/provider/inbox/objection", frozenset({"ROLE_ORGAN_MANAGER"}), None),
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
    # /zones-pack 专题包路由退出本期（D55/P6）：不再映射 shell key。
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
               "provider", "compliance-ops", "zones-pack", "integration-admin"):
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


def test_manager_cannot_access_inline_catalog_wizard() -> None:
    # 部门管理员从 wizard 切角色应被踢到目录审核收件箱（由 defaultRouteForRole 处理）
    assert not _is_route_allowed(
        "/provider/wizard/inline-catalog", "ROLE_ORGAN_MANAGER"
    )
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


def test_hookup_review_only_busiaudit() -> None:
    assert _is_route_allowed("/provider/inbox/hookup-review", "ROLE_BUSIAUDIT")
    assert not _is_route_allowed(
        "/provider/inbox/hookup-review", "ROLE_ORGAN_MANAGER"
    )


def test_field_decision_only_busiaudit() -> None:
    assert _is_route_allowed(
        "/provider/inbox/field-decision/abc", "ROLE_BUSIAUDIT"
    )
    assert not _is_route_allowed(
        "/provider/inbox/field-decision/abc", "ROLE_ORGAN_OPERATER"
    )


def test_provider_inbox_objection_manager_only() -> None:
    assert _is_route_allowed(
        "/provider/inbox/objection/xyz", "ROLE_ORGAN_MANAGER"
    )
    assert not _is_route_allowed(
        "/provider/inbox/objection/xyz", "ROLE_BUSIAUDIT"
    )


def test_national_ext_elem_manager_and_busiaudit_only() -> None:
    # C5：部门管理员 + 业务运营员可进国家扩展要素编制；操作员不可见。
    assert _is_route_allowed("/provider/national-ext-elem", "ROLE_ORGAN_MANAGER")
    assert _is_route_allowed("/provider/national-ext-elem", "ROLE_BUSIAUDIT")
    assert not _is_route_allowed("/provider/national-ext-elem", "ROLE_ORGAN_OPERATER")


def test_reverse_catalog_wizard_manager_only() -> None:
    assert _is_route_allowed(
        "/provider/wizard/reverse-catalog", "ROLE_ORGAN_MANAGER"
    )
    assert not _is_route_allowed(
        "/provider/wizard/reverse-catalog", "ROLE_ORGAN_OPERATER"
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
