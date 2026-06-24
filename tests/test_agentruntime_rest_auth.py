"""R-004 / R-001 安全契约：/api/agent-runtime/tasks 的 role 不得来自 request body。

这些用例不依赖 agent_runtime SDK 包安装，直接验证 RestHandler 的 role 派生函数。
"""
from __future__ import annotations

import inspect

import pytest

from zw_brain.entry.rest.server import RestHandler
from zw_brain.shared.auth_context import AuthContext, reset_auth_context, set_auth_context

pytestmark = pytest.mark.no_db


def _auth_ctx(role_codes: tuple[str, ...]) -> AuthContext:
    return AuthContext(
        subject="u1",
        username="u1",
        tenant_id="sd-default",
        org_code="dev",
        role_codes=role_codes,
        claims={},
    )


def test_role_from_verified_identity_downgrades_unauthorized_body_role() -> None:
    """body 请求 ROLE_SYSTEM 但 token 仅授予 OPERATER → 降权到 OPERATER。"""
    token = set_auth_context(_auth_ctx(("ROLE_ORGAN_OPERATER",)))
    try:
        handler = RestHandler.__new__(RestHandler)
        assert handler._role_from_verified_identity("ROLE_SYSTEM") == "ROLE_ORGAN_OPERATER"
        assert handler._role_from_verified_identity("ROLE_ORGAN_OPERATER") == "ROLE_ORGAN_OPERATER"
        assert handler._role_from_verified_identity("") == "ROLE_ORGAN_OPERATER"
    finally:
        reset_auth_context(token)


def test_role_from_verified_identity_returns_empty_for_no_product_role() -> None:
    """identity 未持有任何 product role → 返回空，POST handler 应 403。"""
    token = set_auth_context(_auth_ctx(("ROLE_UNKNOWN_NON_PRODUCT",)))
    try:
        handler = RestHandler.__new__(RestHandler)
        assert handler._role_from_verified_identity("ROLE_SYSTEM") == ""
        assert handler._role_from_verified_identity("") == ""
    finally:
        reset_auth_context(token)


def test_role_from_verified_identity_returns_empty_when_no_auth_context() -> None:
    """无 auth_context（未登录路径）→ 派生空 role。"""
    handler = RestHandler.__new__(RestHandler)
    assert handler._role_from_verified_identity("ROLE_SYSTEM") == ""


def test_post_handler_routes_cookieless_path_through_verified_identity() -> None:
    """静态契约：cookie-less 分支必须调 _role_from_verified_identity，不得直接信任 body role。"""
    src = inspect.getsource(RestHandler._handle_agent_runtime_task_post)
    assert "_role_from_verified_identity(requested_role)" in src, (
        "cookie-less 路径必须经 _role_from_verified_identity 派生 role（R-004 安全契约）"
    )
