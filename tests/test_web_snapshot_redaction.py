from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.command.brain import BrainService
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared.state_store import StateStore


def test_role_organ_operater_strips_capability_packages_but_keeps_delivery() -> None:
    """D23 retrofit: 部门操作员承接旧 R1（申请人）/R3/R4（基层填报人）三视角。
    R-002 取舍：在该折叠下保留申请人对 delivery_tasks 的可见性（J1 闭环需要看交付回执），
    基层填报人专属"不可见"语义已无法在 role 层独立表达——若未来引入 perspective/sub-role
    维度，再恢复差异化裁剪。capability_packages 仍对部门操作员不可见（跨租户接入仅 BUSIAUDIT）。
    """
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        full = svc.snapshot()
        out = redact_webui_snapshot(full, "ROLE_ORGAN_OPERATER")
        assert out["capability_packages"] == []
        assert len(full["capability_packages"]) > 0
        # 部门操作员（含申请人视角）keeps delivery_tasks
        assert len(out["delivery_tasks"]) > 0
        # 安全管理员（与业务流程解耦）应当看不到 delivery_tasks（_DELIVERY 不含此角色）
        sec_admin_out = redact_webui_snapshot(full, "ROLE_SECURITY_ADMIN")
        assert sec_admin_out["delivery_tasks"] == [], "ROLE_SECURITY_ADMIN 不应看到原始交付任务"
        # 平台运维员（不参与业务旅程）同样应当看不到
        sys_out = redact_webui_snapshot(full, "ROLE_SYSTEM")
        assert sys_out["delivery_tasks"] == [], "ROLE_SYSTEM 不应看到原始交付任务"


def test_redact_r7_keeps_capability_packages_others_lose_them() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        full = svc.snapshot()
        # Sanity: fixture must seed packages or the redaction decision below is vacuous.
        assert full["capability_packages"], "fixture seed must include capability packages"
        r7_out = redact_webui_snapshot(full, "ROLE_BUSIAUDIT")
        r3_out = redact_webui_snapshot(full, "ROLE_ORGAN_OPERATER")
        # 业务运营员 sees the original set (preservation, not just non-empty);
        # 镇街填报人 sees an empty list (consistent with the 基层填报人-as-blocked convention
        # used in test_redact_r1_strips_capability_packages_but_keeps_delivery).
        assert r7_out["capability_packages"] == full["capability_packages"]
        assert r3_out["capability_packages"] == []


def test_invoke_system_snapshot_uses_role_payload() -> None:
    with TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "state.json")
        svc = BrainService(state_store=store)
        snap_r1 = svc.invoke_skill("system.snapshot", {"role": "ROLE_ORGAN_OPERATER"})
        snap_r7 = svc.invoke_skill("system.snapshot", {"role": "ROLE_BUSIAUDIT"})
        assert snap_r1["capability_packages"] == []
        assert len(snap_r7["capability_packages"]) > 0
