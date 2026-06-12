"""工作台问候语 = 真实会话身份现算（#258 复审 R-004 收尾，0611 战役零碎批次）。

守护点：
  - seed_snapshot.json workbench 各角色桶不再携带 greeting（虚构人物名「周处长/刘主任/
    高主任/林督查」整体退役，防回潮钉死）。
  - workbench.view 问候语按会话现算：trusted payload 携带 actor_snapshot.display_name
    （IAM 登录=actor_projection 真名；dev-bypass=「本地调试」）则带出；取不到诚实回落
    纯时段问候（上午好/下午好/晚上好），不捏造姓名头衔（D11/R12）。
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.command.handlers.j1.workbench import _session_greeting

REPO_ROOT = Path(__file__).resolve().parents[1]
TIME_GREETINGS = ("上午好", "下午好", "晚上好")
RETIRED_FICTIONAL_NAMES = ("周处长", "刘主任", "高主任", "林督查")


# ─── seed 防回潮 ─────────────────────────────────────────────────────────────

def test_seed_workbench_carries_no_greeting() -> None:
    seed = json.loads((REPO_ROOT / "zw_brain" / "domain" / "seed_snapshot.json").read_text(encoding="utf-8"))
    for role, bucket in seed["workbench"].items():
        assert "greeting" not in bucket, f"{role} 桶回潮了 seed greeting（虚构人物名已退役，问候语由会话现算）"


# ─── _session_greeting 单元 ──────────────────────────────────────────────────

def test_session_greeting_uses_display_name_when_present() -> None:
    greeting = _session_greeting({"actor_snapshot": {"display_name": "张三"}})
    assert greeting.startswith("张三，")
    assert greeting.removeprefix("张三，") in TIME_GREETINGS


def test_session_greeting_falls_back_honestly_without_identity() -> None:
    # in-process / 离线：无 actor_snapshot 或无 display_name → 纯时段问候，不捏造。
    for payload in ({}, {"actor_snapshot": {}}, {"actor_snapshot": {"display_name": "  "}}, {"actor_snapshot": None}):
        greeting = _session_greeting(payload)
        assert greeting in TIME_GREETINGS, greeting


# ─── handler 端到端（invoke_skill 真分发） ───────────────────────────────────

@pytest.fixture()
def brain(monkeypatch: pytest.MonkeyPatch):
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "workbench_greeting.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        from zw_brain.shared import db as db_module
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        from zw_brain.shared.migrate import ensure_runtime_schema
        ensure_runtime_schema()

        import zw_brain.shared.audit as audit_bus
        from zw_brain.command.brain import BrainService
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.state_store import StateStore

        ds = DatabaseStore()
        audit_bus.configure_sink(ds.append_audit_event)
        yield BrainService(state_store=StateStore(database_store=ds))
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def test_workbench_view_greeting_from_session_display_name(brain) -> None:
    snapshot = actor_snapshot("ROLE_ORGAN_OPERATER", display_name="测试操作员")
    result = invoke_trusted(brain, "workbench.view", {"role": "ROLE_ORGAN_OPERATER"}, role="ROLE_ORGAN_OPERATER", snapshot=snapshot)
    assert result["greeting"].startswith("测试操作员，")


def test_workbench_view_greeting_honest_fallback_and_no_fiction(brain) -> None:
    # 测试默认 actor_snapshot 无 display_name → 纯时段问候；且任何角色都不再出现虚构人物名。
    for role in ("ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"):
        greeting = invoke_trusted(brain, "workbench.view", {"role": role}, role=role)["greeting"]
        assert greeting in TIME_GREETINGS, (role, greeting)
        for name in RETIRED_FICTIONAL_NAMES:
            assert name not in greeting
