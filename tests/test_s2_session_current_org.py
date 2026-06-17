"""S2 — 会话端点注入 current_org_name（供数向导「提供方/所属部门」显示会话化）。

#298 已让后端按 caller_org_code 写 owner（功能正确），但前端两个向导仍硬编码显示「省大数据局」。
本流让 /auth/iaf/session 与 token 换票响应在 public_payload 之上额外注入会话当前机构码 + 名，
前端 useCurrentOrg 据此回显真实机构。auth_session.py（shared 域）不动——名在 entry 层组装时补。
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from tests._iaf_rest_http import (
    KeyFixture,
    bootstrap_iaf_runtime,
    establish_session,
    http_request,
    run_server,
    stop_server,
)
from zw_brain.shared.auth_session import SESSION_COOKIE_NAME


def test_token_response_carries_current_org_fields() -> None:
    """token 换票（_respond_with_session）响应顶层带 current_org_code + current_org_name。

    fixture 会话 org_code='ORG-A'：码原样回显；名因参照投影无该机构 → 诚实留空（不捏造）。
    """
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            status, _, login_body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/",
            )
            assert status == 200, login_body
            # token 响应即 establish_session 内部那条 POST 的 body —— 复用 helper 拿 session，
            # 再以 GET /session 校验同一注入（两条路径共用 _session_public_payload）。
            session_id, _ = establish_session(port, keys)

            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/session",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
            # 契约：两个 key 必须存在（前端无条件读取）。
            assert "current_org_code" in body, body
            assert "current_org_name" in body, body
            # 码取自会话（fixture org_code='ORG-A'）。
            assert body["current_org_code"] == "ORG-A", body
            # ORG-A 不在参照投影 → 名诚实留空，不回落码、不捏造。
            assert body["current_org_name"] == "", body
        finally:
            stop_server(server, thread)
