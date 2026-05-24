"""F4 integration tests — B1.2 capability.package.* 后端（e4-b1-agentruntime）。

覆盖 supervisor 列的 6 case：
  (a) 能力包审核 draft → pending → approved 状态机（走既有 package.review_decide
      verify F4 不破现有 lifecycle）
  (b) 启用/停用 audit 写入 write-critical（走既有 tenant.capability.enable/disable
      verify F4 多签 sink 仍工作）
  (c) 回滚到上一版本（F4 package.rollback）
  (d) 暴露矩阵 list 返回 209 manifest 的 compatibility 字段（F4
      package.exposure.matrix.query）
  (e) trust_level 升降级（F4 package.trust_level.update —— manifest 业务字段，
      非 AgentRuntime Registry）
  (f) tenant_scope 越权场景拦下（package.exposure.matrix.query；写类走
      enforce_manifest_policy 已在其他套件覆盖）

不覆盖：B1.2 UI（F5）、AgentRuntime Registry 4 字段（F6 T1 触发）、F7 5 borderline
报表 sign-off。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TENANT = "sd-default"


@pytest.fixture
def brain_with_audit(tmp_path, monkeypatch):
    """Bootstrap full brain service with audit sink wired to a temp AuditStore.

    Each test gets its own SQLite for runtime + audit；不污染主 .data/zw_brain.db。
    """
    db_path = tmp_path / "runtime.db"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.setenv("ZW_BRAIN_AUDIT_DB_PATH", str(tmp_path / "audit.db"))

    # Force singletons re-init so monkeypatched env paths take effect
    from zw_brain.command import runtime as runtime_mod
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.audit import store as audit_store_mod

    audit_store_mod.set_default_store(None)
    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()

    service = runtime_mod.get_service()
    yield service

    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_store_mod.set_default_store(None)


def _new_package(brain) -> str:
    """Seed a capability_package row directly into snapshot for write-path tests.

    Avoids depending on the existing capability.package.register pipeline, which
    is exercised in other test suites — F4 tests want a fresh, deterministic
    fixture under their own control.
    """
    pkg_id = "PKG-F4-TEST-001"
    package = {
        "id": pkg_id,
        "slug": "f4-test",
        "source": "zw-brain registry",
        "status": "active",
        "registeredVersion": "v1.2.0",
        "rollbackTarget": "v1.1.0",
        "exposure": ["api", "webui"],
        "auditClass": "read-normal",
        "desc": "F4 integration test package",
        "trustLevel": "baseline",
        "aiReview": {
            "summary": "stub",
            "missing": [],
            "safe": [],
            "draft": "",
        },
        "contract": {},
        "tenantPolicy": {"scope": "tenant-bound"},
        "failureWriteback": {"target": "audit_event"},
        "runtimeBinding": {"protocol": "brain_service"},
    }
    brain._snapshot.setdefault("capability_packages", []).append(package)
    return pkg_id


# ---------------------------------------------------------------------------
# (a) 现有审核 lifecycle 没坏 —— draft → approved 通过 package.review_decide
# ---------------------------------------------------------------------------


def test_existing_review_lifecycle_still_works_under_multiplex_sink(brain_with_audit) -> None:
    brain = brain_with_audit
    pkg_id = _new_package(brain)
    brain._package_by_id(pkg_id)["status"] = "pending"
    brain._package_by_id(pkg_id)["versionStatus"] = "draft"

    out = invoke_trusted(
        brain,
        "package.review_decide",
        {"package_id": pkg_id, "decision": "approve", "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )
    assert out["ok"] is True
    assert brain._package_by_id(pkg_id)["status"] == "approved"


# ---------------------------------------------------------------------------
# (b) 启停在 multiplex sink 下仍写审计；这里只 smoke-test invoke_skill 链路
# ---------------------------------------------------------------------------


def test_tenant_capability_enable_writes_audit_under_multiplex_sink(brain_with_audit) -> None:
    from zw_brain.shared.audit import index as audit_index
    brain = brain_with_audit
    pkg_id = _new_package(brain)
    # package needs registered version + approved status to enable
    item = brain._package_by_id(pkg_id)
    item["status"] = "approved"
    item["versionStatus"] = "registered"
    item["registeredVersion"] = item.get("registeredVersion") or "v1.0.0"

    out = invoke_trusted(
        brain,
        "tenant.capability.enable",
        {"package_id": pkg_id, "tenant_id": TENANT, "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )
    assert out["ok"] is True
    # multiplex sink 应同时落主 DB + F1 AuditStore；这里只校验 AuditStore 至少
    # 收到一条 tenant.capability.enable 的事件
    events = audit_index.query(skill_id="tenant.capability.enable", limit=10)
    assert len(events) >= 1
    assert any(ev.audit_class == "write-critical" for ev in events)


# ---------------------------------------------------------------------------
# (c) package.rollback —— F4 新 cap，回滚到上一版本
# ---------------------------------------------------------------------------


def test_package_rollback_swaps_active_and_previous_version(brain_with_audit) -> None:
    brain = brain_with_audit
    pkg_id = _new_package(brain)
    out = invoke_trusted(
        brain,
        "package.rollback",
        {"package_id": pkg_id, "reason": "regression in v1.2.0", "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )
    assert out["ok"] is True
    assert out["result"]["previous_version"] == "v1.2.0"
    assert out["result"]["rolled_back_to"] == "v1.1.0"
    item = brain._package_by_id(pkg_id)
    assert item["registeredVersion"] == "v1.1.0"
    assert item["rollbackTarget"] == "v1.2.0"
    assert item["status"] == "rolled-back"


def test_package_rollback_rejects_when_no_rollback_target(brain_with_audit) -> None:
    from zw_brain.command.brain import InvalidStateError

    brain = brain_with_audit
    pkg_id = _new_package(brain)
    brain._package_by_id(pkg_id)["rollbackTarget"] = ""
    with pytest.raises(InvalidStateError):
        invoke_trusted(
            brain,
            "package.rollback",
            {"package_id": pkg_id, "confirmed": True},
            role="ROLE_BUSIAUDIT",
        )


# ---------------------------------------------------------------------------
# (d) package.exposure.matrix.query —— 209 manifest × 5 surface
# ---------------------------------------------------------------------------


def test_exposure_matrix_returns_all_manifests(brain_with_audit) -> None:
    brain = brain_with_audit
    out = invoke_trusted(
        brain,
        "package.exposure.matrix.query",
        {"tenant_id": TENANT},
        role="ROLE_BUSIAUDIT",
    )
    assert out["totals"]["manifests"] >= 200  # 209 currently
    assert "api" in out["totals"]["by_surface"]
    assert "webui" in out["totals"]["by_surface"]
    # 至少几个高频前缀必须出现
    skill_ids = {row["skill_id"] for row in out["matrix"]}
    assert "audit.event.query" in skill_ids
    assert "package.rollback" in skill_ids
    # F4 新 cap trust_level 默认 baseline（manifest 未声明则按 baseline 派生）
    rollback_row = next(r for r in out["matrix"] if r["skill_id"] == "package.rollback")
    assert rollback_row["audit_class"] == "write-critical"
    assert rollback_row["trust_level"] == "baseline"


def test_exposure_matrix_filters_by_journey_and_status(brain_with_audit) -> None:
    brain = brain_with_audit
    out = invoke_trusted(
        brain,
        "package.exposure.matrix.query",
        {"journey": "b1", "status": "live", "tenant_id": TENANT},
        role="ROLE_BUSIAUDIT",
    )
    assert all(r["journey"] == "b1" and r["status"] == "live" for r in out["matrix"])
    assert out["scanned"] >= 47  # B1 budget after F4 = 50


def test_exposure_matrix_filters_by_surface(brain_with_audit) -> None:
    brain = brain_with_audit
    out = invoke_trusted(
        brain,
        "package.exposure.matrix.query",
        {"surface": "mcp", "tenant_id": TENANT},
        role="ROLE_BUSIAUDIT",
    )
    assert all("mcp" in r["surfaces"] for r in out["matrix"])


# ---------------------------------------------------------------------------
# (e) package.trust_level.update —— F4 业务字段升降级
# ---------------------------------------------------------------------------


def test_package_trust_level_update_changes_metadata(brain_with_audit) -> None:
    brain = brain_with_audit
    pkg_id = _new_package(brain)

    out = invoke_trusted(
        brain,
        "package.trust_level.update",
        {"package_id": pkg_id, "trust_level": "reviewed", "reason": "compliance review approved", "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )
    assert out["ok"] is True
    assert out["result"]["previous_trust_level"] == "baseline"
    assert out["result"]["new_trust_level"] == "reviewed"
    assert brain._package_by_id(pkg_id)["trustLevel"] == "reviewed"


def test_package_trust_level_rejects_unknown_level(brain_with_audit) -> None:
    from zw_brain.command.brain import BrainServiceError

    brain = brain_with_audit
    pkg_id = _new_package(brain)
    with pytest.raises(BrainServiceError):
        invoke_trusted(
            brain,
            "package.trust_level.update",
            {"package_id": pkg_id, "trust_level": "ultra-trusted", "confirmed": True},
            role="ROLE_BUSIAUDIT",
        )


def test_trust_level_is_NOT_agentruntime_registry_field(brain_with_audit) -> None:
    """F6 T1 触发前 manifest 不应该有 AgentRuntime Registry 的 4 个字段；
    F4 manifest 业务字段 trust_level 与 Registry 同名字段是不同 scope。

    本测试是合同护栏：以后 F6 land 时如果手抖把字段塞到主 manifest schema 里，
    此测试会立刻红。
    """
    from zw_brain.skill_registration.runtime import load_manifests
    manifests = load_manifests()
    rollback_manifest = manifests["package.rollback"]
    # F4 不动 Registry 字段：4 个字段当前不应存在
    for forbidden in ("runtime_spec_version", "agent_yaml_ref", "workspace_required"):
        assert forbidden not in rollback_manifest, (
            f"manifest 不该包含 AgentRuntime Registry 字段 {forbidden!r}（F6 T1 触发后另开 PR）"
        )
    # trust_level 字段在 manifest 里只作为 F4 业务字段；本 F4 没在 manifest schema
    # 上声明（也不强制），handler 通过 capability_package 表跟踪
    assert "trust_level" not in rollback_manifest


# ---------------------------------------------------------------------------
# (f) tenant_scope 越权
# ---------------------------------------------------------------------------


def test_exposure_matrix_cross_tenant_denied(brain_with_audit) -> None:
    from zw_brain.command.handlers.b1 import intake as intake_handlers
    from zw_brain.domain.policy import DomainAccessDeniedError

    with pytest.raises(DomainAccessDeniedError):
        intake_handlers.handler_package_exposure_matrix_query(
            brain=None,  # type: ignore[arg-type]
            skill_id="package.exposure.matrix.query",
            payload={"tenant_id": "other-tenant"},
        )


# ---------------------------------------------------------------------------
# (g) runtime lifecycle helper unit tests
# ---------------------------------------------------------------------------


def test_validate_package_lifecycle_transition_allows_known() -> None:
    from zw_brain.skill_registration.runtime import validate_package_lifecycle_transition

    # 合法迁移
    validate_package_lifecycle_transition("pending", "approved")
    validate_package_lifecycle_transition("approved", "active")
    validate_package_lifecycle_transition("active", "rolled-back")
    validate_package_lifecycle_transition("rolled-back", "active")
    # 同状态等于 no-op
    validate_package_lifecycle_transition("active", "active")


def test_validate_package_lifecycle_transition_rejects_illegal() -> None:
    from zw_brain.skill_registration.runtime import validate_package_lifecycle_transition

    with pytest.raises(ValueError):
        validate_package_lifecycle_transition("pending", "active")
    with pytest.raises(ValueError):
        validate_package_lifecycle_transition("rejected", "active")
    with pytest.raises(ValueError):
        validate_package_lifecycle_transition("unknown-state", "active")


def test_package_trust_levels_enum_stable() -> None:
    from zw_brain.skill_registration.runtime import package_trust_levels

    assert package_trust_levels() == ("baseline", "reviewed", "restricted", "revoked")
