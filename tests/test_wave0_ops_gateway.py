# Wave: 0
# Journey: B1.1
# Capability: ops.gateway.heartbeat.ingest
# Consumer-faces: API / CLI / A2A
# Roles: ROLE_ORGAN_MANAGER, ROLE_SECURITY_AUDIT
# Trace:
#   .testing/waves/wave-0-golden-path/features/ops-gateway-heartbeat.feature
#   docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md §3.3 / §3.5
#   docs/approved/zw-brain-architecture.md §1.3（D32 边界澄清）
#   CLAUDE.md D32 — A 类 20 条复活按 plan 落地
#   .twin/e6-platform-m0/plan.yaml F12（本文件 = F12.evidence_plan 主证据）
"""Wave 0 第一刀（e6.F12）：ops.gateway.heartbeat.ingest 验收。

承接旧 `/openapi/report`（362,407 调用，Pareto P0）→ plan §3.3
`gateway_runtime_status_projection` read model。

.feature 现列 10 Scenario；本文件覆盖代码可达的后端切面（S1/S2/S3/S5 +
S4 schema / audit / envelope + S7 5 消费面回归）。新增「B1.1 网关运行只读面板」
正向场景 + S6（无权限不渲染 tab）由 tests/e2e/b11_compliance.spec.ts 验收；
S8/S9 由 preflight 段 24/25 机械守卫。读侧 ②→③ 闭合见 B11ComplianceOps.vue
「网关运行」tab（消费 ops.service.report.query）。

数据隔离：每个测试用例创建独立 TemporaryDirectory + 切 ZW_BRAIN_DB_PATH，
ensure_runtime_schema() drop & recreate，零依赖 .data/zw_brain.db seed。
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from sqlalchemy import select

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import AccessDeniedError, BrainService, BrainServiceError
from zw_brain.domain.models import GatewayRuntimeStatusProjectionRecord
from zw_brain.domain.repositories.gateway_runtime import GatewayRuntimeRepository
from zw_brain.domain.serializers.ops_metrics import (
    DEFAULT_GATEWAY_STALE_SECONDS,
    derive_runtime_status,
)
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import _CACHE_LOCK, _ENGINE_CACHE, create_session_factory
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

SKILL = "ops.gateway.heartbeat.ingest"
REPORT_SKILL = "ops.service.report.query"
TENANT = "sd-default"
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def brain():
    """Per-test BrainService bound to a fresh SQLite DB.

    Each test gets its own temp DB so cross-test state never leaks; the
    Wave 0 first cut is verified in isolation, not as a chained scenario.
    """
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "gateway.db")
        prev_path = os.environ.get("ZW_BRAIN_DB_PATH")
        prev_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
        os.environ["ZW_BRAIN_DB_PATH"] = db_path
        os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
        with _CACHE_LOCK:
            _ENGINE_CACHE.clear()
        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        try:
            yield service
        finally:
            with _CACHE_LOCK:
                _ENGINE_CACHE.clear()
            if prev_path is None:
                os.environ.pop("ZW_BRAIN_DB_PATH", None)
            else:
                os.environ["ZW_BRAIN_DB_PATH"] = prev_path
            if prev_url is not None:
                os.environ["ZW_BRAIN_DATABASE_URL"] = prev_url


def _heartbeat_payload(instance_id: str, *, status: str = "online", **extra: Any) -> dict[str, Any]:
    return {
        "gateway_instance_id": instance_id,
        "gateway_address_ref": "10.0.x.x:8080",
        "runtime_profile": "zone-a-prod",
        "status": status,
        "last_reported_at": datetime.now(UTC).isoformat(),
        "source_ref": "redis:GATEWAY_REPORT",
        "confirmed": True,
        **extra,
    }


def _list_rows(
    *,
    instance_id_prefix: str = "gw-zone-",
    tenant_id: str = TENANT,
) -> list[GatewayRuntimeStatusProjectionRecord]:
    """List projection rows scoped to this test's instance prefix.

    Seed snapshot pre-loads ``gw-api-main`` into the projection during
    ``BrainService`` bootstrap; tests assert on their own ``gw-zone-*`` rows
    rather than total count to avoid coupling to seed contents.
    """
    with create_session_factory()() as session:
        return list(
            session.execute(
                select(GatewayRuntimeStatusProjectionRecord)
                .where(
                    GatewayRuntimeStatusProjectionRecord.tenant_id == tenant_id,
                    GatewayRuntimeStatusProjectionRecord.gateway_instance_id.like(f"{instance_id_prefix}%"),
                )
                .order_by(GatewayRuntimeStatusProjectionRecord.gateway_instance_id)
            ).scalars()
        )


# ──────────────────────────────────────────────────────────────────────
# S1 — 首次心跳新建一行 projection
# ──────────────────────────────────────────────────────────────────────


def test_first_heartbeat_creates_projection_row(brain: BrainService) -> None:
    result = invoke_trusted(
        brain,
        SKILL,
        _heartbeat_payload("gw-zone-a-001"),
        role="ROLE_ORGAN_MANAGER",
    )

    rows = _list_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.gateway_instance_id == "gw-zone-a-001"
    assert row.tenant_id == TENANT
    assert row.status == "online"
    assert row.source_ref == "redis:GATEWAY_REPORT"
    assert result["ok"] is True
    assert result["result"]["gateway_instance_id"] == "gw-zone-a-001"


# ──────────────────────────────────────────────────────────────────────
# S2 — 同 instance_id 心跳幂等：仍 1 行，status / last_reported_at 更新
# ──────────────────────────────────────────────────────────────────────


def test_same_instance_id_upserts_in_place(brain: BrainService) -> None:
    invoke_trusted(brain, SKILL, _heartbeat_payload("gw-zone-a-001"),
                   role="ROLE_ORGAN_MANAGER")
    later = _heartbeat_payload("gw-zone-a-001", status="warning",
                               last_reported_at="2026-05-29T12:34:56+00:00")
    invoke_trusted(brain, SKILL, later, role="ROLE_ORGAN_MANAGER")

    rows = _list_rows()
    assert len(rows) == 1, "幂等 upsert 应保持单行，而不是 append"
    assert rows[0].status == "warning"
    assert rows[0].last_reported_at.replace(tzinfo=None) == datetime(2026, 5, 29, 12, 34, 56)


# ──────────────────────────────────────────────────────────────────────
# S3 — 心跳超时 → status 自动转 offline（read-side 派生）
#
# 派生在 ops_metrics_ser.derive_runtime_status / gateway_to_dict 中做，
# projection 的 last_reported_at 真值不被修改（.feature S3 末段约定）。
# 阈值环境变量 ZW_BRAIN_GATEWAY_STALE_SECONDS（默认 180s）。
# 上层入口验证经 ops.service.report.query 走完整 read path。
# ──────────────────────────────────────────────────────────────────────


def test_stale_heartbeat_pure_function_derives_offline() -> None:
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=UTC)
    fresh = now - timedelta(seconds=DEFAULT_GATEWAY_STALE_SECONDS - 1)
    stale = now - timedelta(seconds=DEFAULT_GATEWAY_STALE_SECONDS + 1)

    assert derive_runtime_status("online", fresh, now=now) == "online"
    assert derive_runtime_status("online", stale, now=now) == "offline"
    # offline 是终态：即便后来到 fresh，也不"复活"（一致性边界 — 复活由
    # 下次显式 ingest 心跳触发）
    assert derive_runtime_status("offline", fresh, now=now) == "offline"


def test_stale_heartbeat_derives_offline_on_report_query(brain: BrainService) -> None:
    """Read path：ingest 一条很久之前的心跳 → report query 把它派生成 offline。

    UNIQUE last_reported_at 不被修改：projection 行 status 仍是 ingest 时传入的
    "online"；派生只发生在 gateway_to_dict 序列化层。
    """
    stale_ts = (datetime.now(UTC) - timedelta(seconds=DEFAULT_GATEWAY_STALE_SECONDS + 60)).isoformat()
    invoke_trusted(
        brain, SKILL,
        _heartbeat_payload("gw-zone-b-002", status="online", last_reported_at=stale_ts),
        role="ROLE_ORGAN_MANAGER",
    )

    report = invoke_trusted(brain, REPORT_SKILL, {}, role="ROLE_ORGAN_MANAGER")
    seen = {g["gateway_instance_id"]: g["status"] for g in report["gateways"]}
    assert seen.get("gw-zone-b-002") == "offline", \
        f"read-side stale 派生失败：{seen!r}"

    # 真值未被人为修改 — projection 行 status 仍是 online
    rows = _list_rows(instance_id_prefix="gw-zone-b-")
    assert rows and rows[0].status == "online"


# ──────────────────────────────────────────────────────────────────────
# S5 — 跨租户 gateway_instance_id 隔离（UNIQUE 复合键含 tenant_id）
# ──────────────────────────────────────────────────────────────────────


def test_cross_tenant_same_instance_id_is_isolated(brain: BrainService) -> None:
    """sd-default 与 other-tenant 同名 gw-zone-shared-01 写两行不串。

    多租户 invoke_skill 链路不在 Wave 0 范围（基线 §8.2 单租户假设）；
    本 test 直接 hit repo 验证 UNIQUE(tenant_id, gateway_instance_id) 复合键边界。
    跨租户经 invoke_skill 的回归归 wave-3 multi-tenant-policy.feature。
    """
    invoke_trusted(brain, SKILL, _heartbeat_payload("gw-zone-shared-01", status="online"),
                   role="ROLE_ORGAN_MANAGER")

    other_repo = GatewayRuntimeRepository()
    other_repo.upsert_heartbeat(
        {
            "gateway_instance_id": "gw-zone-shared-01",
            "gateway_address_ref": "10.99.x.x:8080",
            "runtime_profile": "other-tenant-prod",
            "status": "offline",
            "last_reported_at": datetime.now(UTC).isoformat(),
            "source_ref": "redis:GATEWAY_REPORT@other",
        },
        tenant_id="other-tenant",
    )

    sd_rows = _list_rows(tenant_id="sd-default")
    other_rows = _list_rows(tenant_id="other-tenant")

    assert len(sd_rows) == 1 and sd_rows[0].status == "online"
    assert len(other_rows) == 1 and other_rows[0].status == "offline"
    assert sd_rows[0].gateway_address_ref != other_rows[0].gateway_address_ref


# ──────────────────────────────────────────────────────────────────────
# S4 附加 — manifest required schema 校验：缺 gateway_instance_id
#
# 注：S4 本文 ".feature 缺 tenant_id 拒" 是多租户隔离边界，本 PR 范围下
# tenant_id 由 build_trusted_skill_payload(actor_snapshot.tenant_id) 注入，
# 客户端 payload 无 tenant_id 字段（manifest 也未 require），由 trusted-session
# 路径已机械保证。本测试只覆盖 manifest 字面 required 集合。
# ──────────────────────────────────────────────────────────────────────


def test_missing_required_field_rejected(brain: BrainService) -> None:
    bad = _heartbeat_payload("placeholder")
    bad.pop("gateway_instance_id")
    with pytest.raises(BrainServiceError) as exc:
        invoke_trusted(brain, SKILL, bad, role="ROLE_ORGAN_MANAGER")
    assert "gateway_instance_id" in str(exc.value)


# ──────────────────────────────────────────────────────────────────────
# 附加 — 权限：ROLE_ORGAN_OPERATER 不在 execute 集合 → AccessDeniedError
# （.feature S6 的 invoke 侧；WebUI 不渲染入口归 webui 仓库测试栈）
# ──────────────────────────────────────────────────────────────────────


def test_unauthorized_role_is_denied(brain: BrainService) -> None:
    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain,
            SKILL,
            _heartbeat_payload("gw-zone-a-001"),
            role="ROLE_ORGAN_OPERATER",
        )
    assert _list_rows() == [], "拒绝后不应留下任何 projection 行"


# ──────────────────────────────────────────────────────────────────────
# 附加 — 审计落库 + envelope 形态（.feature S1 末两节抽出）
# ──────────────────────────────────────────────────────────────────────


def test_heartbeat_emits_audit_feed_and_envelope(brain: BrainService) -> None:
    result = invoke_trusted(
        brain, SKILL, _heartbeat_payload("gw-zone-a-001"),
        role="ROLE_ORGAN_MANAGER",
    )

    assert set(result.keys()) >= {"ok", "result", "audit_id"}
    assert result["ok"] is True
    assert result["audit_id"], "audit_id 必须由 IdentityMiddleware 注入"
    inner = result["result"]
    assert inner["gateway_instance_id"] == "gw-zone-a-001"
    assert inner["status"] == "online"
    assert inner["source_ref"] == "redis:GATEWAY_REPORT"
    assert "last_reported_at" in inner and "generated_at" in inner

    feed = brain.snapshot()["audit_events"]
    matched = [e for e in feed
               if e.get("type") == "ops.gateway.heartbeat"
               and e.get("target") == "gw-zone-a-001"]
    assert matched, f"未找到 ops.gateway.heartbeat audit feed: {feed!r}"
    assert matched[-1].get("result") == "ok"


# ──────────────────────────────────────────────────────────────────────
# S7 — 5 消费面投影一致回归（manifest 字段集合在 WebUI/API/CLI/MCP/A2A 同步）
#
# 进 test suite 而不是只在 commit 描述里 --check，让下个 PR 改 manifest
# 漏字段被 CI 直接拦下。
# ──────────────────────────────────────────────────────────────────────


def test_5_consumer_contract_export_no_drift() -> None:
    script = REPO_ROOT / "scripts" / "export_agent_contract.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"export_agent_contract.py --check exit={proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "OK" in proc.stdout, proc.stdout
