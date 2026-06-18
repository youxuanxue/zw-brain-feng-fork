#!/usr/bin/env python3
"""check_no_token_role_authz.py — preflight 段 73（D62 A3 回潮守卫）.

不变量：**IAM/IAF token 的角色绝不作为 zw-brain 产品授权的事实源**。产品角色的唯一权威
源是 zw-brain 自有的 ``actor_org_role_binding``（D62）。具体机械钉死：

1. REST 真实身份的产品角色由 binding 派生：``server._bind_auth`` 在非 dev-bypass 分支必须
   用 ``_binding_role_codes_for_subject(...)`` 覆盖 ``AuthContext.role_codes``（token 角色只
   用于身份/签名，绝不直接进授权）。
2. ``_binding_role_codes_for_subject`` 必须读 binding（``list_active_actor_contexts``），
   且**不得**从 token claims 取角色（``role_codes_from_claims``）。
3. 共享边界解析器 ``auth_context.resolve_role_from_identity`` 不得调用
   ``role_codes_from_claims``（它读 ctx.role_codes —— 现由 binding 注入）。

为什么：D62 反转「产品角色从通用共享 IAM token 派生」。通用 realm 跨多产品共享，其
realm_access/resource_access 角色是 IdP plumbing，不是 zw-brain 的 5 角色模型。若未来有人
重新让 token 角色直接授权，两主人漂移 + 越权回潮即复发。本守卫把该收口结构性钉死。

退出码：0 = 不变量成立；1 = 回潮。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "zw_brain" / "entry" / "rest" / "server.py"
AUTH_CTX = REPO / "zw_brain" / "shared" / "auth_context.py"


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    end = text.find(end_marker, start + len(start_marker))
    return text[start : end if end != -1 else len(text)]


def main() -> int:
    errors: list[str] = []

    if not SERVER.exists() or not AUTH_CTX.exists():
        print("[no-token-role-authz] FAIL: 关键文件缺失（server.py / auth_context.py）", file=sys.stderr)
        return 1

    server = SERVER.read_text(encoding="utf-8")
    auth = AUTH_CTX.read_text(encoding="utf-8")

    # 1) _bind_auth 非 bypass 分支必须用 binding 覆盖 role_codes
    bind_auth = _section(server, "def _bind_auth(", "\n    def ")
    if "if not development_iam_bypass:" not in bind_auth or "_binding_role_codes_for_subject(" not in bind_auth:
        errors.append(
            "server._bind_auth 非 dev-bypass 分支未用 _binding_role_codes_for_subject 覆盖 role_codes"
            "——真实身份的产品角色必须来自 binding，不得直接用 token 角色（D62 A2/A3）。"
        )

    # 2) binding helper 必须读 binding、不得读 token 角色
    helper = _section(server, "def _binding_role_codes_for_subject(", "\ndef ")
    if "list_active_actor_contexts(" not in helper:
        errors.append("_binding_role_codes_for_subject 未读 actor_org_role_binding（list_active_actor_contexts）。")
    if "role_codes_from_claims" in helper:
        errors.append("_binding_role_codes_for_subject 不得从 token claims 取角色（role_codes_from_claims）。")

    # 3) 共享边界解析器不得从 token claims 取授权角色
    resolver = _section(auth, "def resolve_role_from_identity(", "\ndef ")
    if "role_codes_from_claims" in resolver:
        errors.append("auth_context.resolve_role_from_identity 不得调用 role_codes_from_claims（应读 ctx.role_codes，由 binding 注入）。")

    if errors:
        print("[no-token-role-authz] FAIL: token 角色授权回潮（D62 A3）：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("[no-token-role-authz] OK: 产品授权角色单一事实源 = actor_org_role_binding，token 角色不进授权（D62 A3）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
