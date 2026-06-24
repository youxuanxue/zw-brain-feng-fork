"""dev-bypass-login ?org= 机构覆盖单测——「真·双账号」浏览器 e2e 的使能改动。

dev-bypass 会话所属机构原由 ZW_BRAIN_DEV_IAM_BYPASS_ORG env 钉死（一栈一机构），故单栈
无法起两个不同部门会话验部门隔离。本改动让 dev-bypass-login 接受可选 ?org=<码> 覆盖会话机构
（仅 dev 档，已 fail-closed 于 get_dev_iam_bypass_enabled）。此测锁定 override 穿到 session
actor_snapshot.current_org_code + claims.org_code；缺省回落 env/'dev' 不变。
"""

from __future__ import annotations

import os

import pytest

from zw_brain.entry.rest import server

pytestmark = pytest.mark.no_db

ORG_A = "11370000MB284651XL"
ORG_B = "360002222211"


def test_org_override_threads_to_profile_and_claims() -> None:
    prof_a = server._dev_iam_bypass_user_profile(ORG_A)
    assert prof_a["current_org_code"] == ORG_A, "override 机构应成为会话当前机构"
    assert prof_a["org_code"] == ORG_A
    assert server._dev_iam_bypass_claims(ORG_A)["org_code"] == ORG_A

    # 不同机构 → 不同会话机构（单栈两会话可分别钉两部门，浏览器 e2e 据此双账号）。
    prof_b = server._dev_iam_bypass_user_profile(ORG_B)
    assert prof_b["current_org_code"] == ORG_B
    assert prof_a["current_org_code"] != prof_b["current_org_code"]


def test_blank_or_missing_override_falls_back_to_env_default() -> None:
    env_default = (os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS_ORG") or "dev").strip() or "dev"
    for arg in (None, "", "   "):
        prof = server._dev_iam_bypass_user_profile(arg)
        assert prof["current_org_code"] == env_default, f"override={arg!r} 应回落 env 默认"
        assert server._dev_iam_bypass_claims(arg)["org_code"] == env_default
