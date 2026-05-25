# Wave: 1
# Journey: J1
# Pages: P4 凭据领取
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER (申请人 / 凭据所有者) | ROLE_ORGAN_MANAGER (审批人)
# Trace:
#   .twin/e1-j1-journey/plan.yaml F5
#   zw_brain/command/handlers/j1/credential.py
#   zw_brain/skill_registration/registered/credential.sample.render.json
"""F5: P4 凭据领取生产化 — credential.issue → query → sample.render 三语样例 + audit chain.

数据隔离：shadow DB（与 W0/F1-F4 一致）。
真实 sd-default 资源：从 catalog_entry / resource_asset 取一条作 resource_id 锚。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed
from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_credential_shadow.db"
TENANT = "sd-default"

require_real_seed({"catalog_entry": 100})


@pytest.fixture(scope="module", autouse=True)
def _shadow_db() -> None:
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    shutil.copy(SEED_DB, SHADOW_DB)
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    yield


@pytest.fixture(scope="module")
def real_resource() -> dict:
    """从真实 sd-default 取一条 catalog_entry 作 resource 锚."""
    with sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT catalog_code, title FROM catalog_entry "
            "WHERE tenant_id=? ORDER BY catalog_code LIMIT 1",
            (TENANT,),
        ).fetchone()
    assert row is not None
    return {"resource_id": row[0], "resource_name": row[1]}


@pytest.fixture(scope="module")
def brain():
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _inject_approved_request(brain, request_id: str, real_resource: dict) -> None:
    """注入一个 approved 申请 + pending delivery_task，让 credential.issue 能签发."""
    brain._snapshot.setdefault("requests", [])
    brain._snapshot.setdefault("delivery_tasks", [])

    # 移除可能的旧记录（idempotent）
    brain._snapshot["requests"] = [r for r in brain._snapshot["requests"] if r.get("id") != request_id]
    brain._snapshot["delivery_tasks"] = [t for t in brain._snapshot["delivery_tasks"] if t.get("requestId") != request_id]

    brain._snapshot["requests"].append({
        "id": request_id,
        "status": "approved",
        "applicant": "U_OP_F5",
        "applicantDept": "部门A_公安",
        "resourceId": real_resource["resource_id"],
        "resourceName": real_resource["resource_name"],
        "purpose": "F5 凭据样例验证",
        "auditId": "AE-F5-test",
    })
    brain._snapshot["delivery_tasks"].append({
        "id": f"DT-{request_id}",
        "requestId": request_id,
        "resourceId": real_resource["resource_id"],
        "resourceName": real_resource["resource_name"],
        # DeliveryRepository.upsert_from_delivery 必填字段
        "status": "granted",
        "state": "granted",
        "channel": "api",
        "accessGrantSnapshot": {},
        "history": [],
    })


def _invoke(brain, skill_id: str, payload: dict) -> dict:
    role = payload.pop("role", "ROLE_ORGAN_MANAGER")
    out = invoke_trusted(brain, skill_id, payload, role=role)
    # write caps wrap as {"result": ..., "audit_id": ...}; read caps return direct dict
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


# ──────────────────────────────────────────────────────────────────────
# credential.issue → query (现有 cap 行为复用验证)
# ──────────────────────────────────────────────────────────────────────


def test_credential_issue_writes_app_key_and_secret(brain, real_resource):
    _inject_approved_request(brain, "REQ-F5-001", real_resource)
    result = _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-001",
        "role": "ROLE_ORGAN_MANAGER",
        "confirmed": True,
    })
    cred = result["credential"]
    assert cred["app_key"].startswith("AK-DEMO-")
    assert cred["app_secret"].startswith("SK-DEMO-")
    assert cred["quota_per_day"] == 1000
    assert "valid_from" in cred and "valid_to" in cred
    assert cred["invoke_url_template"].startswith("https://")


def test_credential_query_returns_issued_credential(brain, real_resource):
    _inject_approved_request(brain, "REQ-F5-002", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-002", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    result = _invoke(brain, "credential.query", {
        "request_id": "REQ-F5-002", "role": "ROLE_ORGAN_OPERATER",
    })
    assert result["status"] == "issued"
    assert result["credential"]["app_key"].startswith("AK-DEMO-")
    assert result["issued_audit_id"] is not None


# ──────────────────────────────────────────────────────────────────────
# F5 核心：credential.sample.render 三语样例
# ──────────────────────────────────────────────────────────────────────


def test_sample_render_returns_three_languages(brain, real_resource):
    _inject_approved_request(brain, "REQ-F5-SAMPLE", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-SAMPLE", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    out = _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-SAMPLE", "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["status"] == "rendered"
    samples = out["samples"]
    assert set(samples.keys()) == {"curl", "python", "java"}
    # 每种语言都含 app_key + invoke_url + quota
    app_key = out["credential_excerpt"]["app_key"]
    invoke_url = out["invoke_url"]
    assert app_key in samples["curl"] and invoke_url in samples["curl"]
    assert "curl -X POST" in samples["curl"]
    assert app_key in samples["python"] and "requests.post" in samples["python"]
    assert "X-App-Key" in samples["python"]
    assert app_key in samples["java"] and "HttpClient" in samples["java"]
    assert "HttpRequest" in samples["java"]
    # quota 在每个样例首行注释里
    assert "quota_per_day=1000" in samples["curl"]
    assert "quota_per_day=1000" in samples["python"]
    assert "quota_per_day=1000" in samples["java"]


def test_sample_render_resource_id_from_real_sd_default(brain, real_resource):
    _inject_approved_request(brain, "REQ-F5-REAL", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-REAL", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    out = _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-REAL", "role": "ROLE_ORGAN_OPERATER",
    })
    # invoke_url 必须 substitute 真实 resource_id（不留 <resource_code> 占位符）
    assert "<resource_code>" not in out["invoke_url"]
    assert real_resource["resource_id"] in out["invoke_url"]
    # resource_name 透传到 samples 注释
    if real_resource["resource_name"]:
        assert real_resource["resource_name"] in out["samples"]["curl"]


def test_sample_render_monitoring_link_no_inline_dashboard(brain, real_resource):
    """监控入口仅外链 §3.4 集团运维监控，不内嵌 dashboard."""
    _inject_approved_request(brain, "REQ-F5-MON", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-MON", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    out = _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-MON", "role": "ROLE_ORGAN_OPERATER",
    })
    link = out["monitoring_link"]
    assert link.startswith("https://"), f"monitoring_link must be external URL: {link}"
    assert "monitoring" in link
    app_key = out["credential_excerpt"]["app_key"]
    assert app_key in link, "monitoring 跳转应携带 app_key 用于过滤本凭据的调用记录"
    assert "§3.4" in out["monitoring_hint"]
    assert "不内嵌" in out["monitoring_hint"]


def test_sample_render_returns_not_issued_when_no_credential(brain, real_resource):
    """凭据未签发时不渲染样例，返回 not_issued + hint."""
    _inject_approved_request(brain, "REQ-F5-EMPTY", real_resource)
    # 不调用 credential.issue，直接 sample.render
    out = _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-EMPTY", "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["status"] == "not_issued"
    assert out["samples"] is None
    assert "未签发" in out["hint"]


# ──────────────────────────────────────────────────────────────────────
# Audit chain
# ──────────────────────────────────────────────────────────────────────


def test_audit_chain_contains_issue_and_sample_render(brain, real_resource):
    _inject_approved_request(brain, "REQ-F5-AUDIT", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-AUDIT", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-AUDIT", "role": "ROLE_ORGAN_OPERATER",
    })
    feed = brain.snapshot()["audit_events"]
    types_on_target = [e["type"] for e in feed if e.get("target") == "REQ-F5-AUDIT"]
    assert "credential.issue" in types_on_target
    assert "credential.sample.render" in types_on_target


# ──────────────────────────────────────────────────────────────────────
# Quota 默认值 + 可改值 (本期默认 1000，未来由 credential.issue 入参覆盖)
# ──────────────────────────────────────────────────────────────────────


def test_quota_default_is_1000_per_day(brain, real_resource):
    _inject_approved_request(brain, "REQ-F5-QUOTA", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-QUOTA", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    out = _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-QUOTA", "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["credential_excerpt"]["quota_per_day"] == 1000


# ──────────────────────────────────────────────────────────────────────
# 安全硬约束：no hardcoded secret leakage
# ──────────────────────────────────────────────────────────────────────


def test_sample_does_not_leak_foreign_credentials(brain, real_resource):
    """守卫样例不混入任何异源生产密钥串（ssh-rsa / aws_secret / private key 等）。
    注：sample 本身按设计渲染用户自己的 demo prefix AK-DEMO/SK-DEMO；本测试只防异源 secret 串。
    用户自己 app_secret 的跨角色暴露由 policy.py credential.sample.render.execute 收敛到
    ROLE_ORGAN_OPERATER 保证（见下方 test_sample_render_denies_non_applicant_role）。"""
    _inject_approved_request(brain, "REQ-F5-NOLEAK", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-NOLEAK", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    out = _invoke(brain, "credential.sample.render", {
        "request_id": "REQ-F5-NOLEAK", "role": "ROLE_ORGAN_OPERATER",
    })
    blob = (out["samples"]["curl"] + out["samples"]["python"] + out["samples"]["java"]).lower()
    for forbidden in (
        "begin private key", "ssh-rsa ", "aws_secret_access_key",
        "aliyun_access", "github_pat_", "client_secret=", "password=",
    ):
        assert forbidden not in blob, f"forbidden secret-like token leaked: {forbidden}"


def test_sample_render_denies_audit_roles(brain, real_resource):
    """R-001 配套守卫：credential.sample.render.execute 收敛到 credential 自然生命周期角色
    (申请人 ROLE_ORGAN_OPERATER + 审批人 ROLE_ORGAN_MANAGER 通过 ROLE_HIERARCHY 继承)；
    审计角色 (BUSIAUDIT 平台复核 / SECURITY_AUDIT 安全审计) 不应通过 sample.render 复制
    含 app_secret 的样例 — 走 credential.query + audit_event 验证签发足矣
    (principle of least privilege)。"""
    from zw_brain.command.brain import AccessDeniedError
    from zw_brain.domain.policy import permissions_for_role

    _inject_approved_request(brain, "REQ-F5-DENY", real_resource)
    _invoke(brain, "credential.issue", {
        "request_id": "REQ-F5-DENY", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    # 审计角色不应持有 credential.sample.render.execute
    for denied_role in ("ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"):
        perms = permissions_for_role(denied_role)
        assert "credential.sample.render.execute" not in perms, \
            f"{denied_role} 仍持有 sample.render 权限 — R-001 fix 失效"
    # credential 生命周期角色仍持有（申请人直接, 审批人通过 ROLE_HIERARCHY 继承）
    for allowed_role in ("ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"):
        perms = permissions_for_role(allowed_role)
        assert "credential.sample.render.execute" in perms, \
            f"{allowed_role} 应持有 sample.render 权限"
    # 通过 brain.invoke_skill 链路验证 BUSIAUDIT 实际被拒
    try:
        _invoke(brain, "credential.sample.render", {
            "request_id": "REQ-F5-DENY", "role": "ROLE_BUSIAUDIT",
        })
    except AccessDeniedError as exc:
        assert "credential.sample.render" in str(exc), exc
    else:
        raise AssertionError("ROLE_BUSIAUDIT 走 invoke_skill 未被 policy 拒绝")
