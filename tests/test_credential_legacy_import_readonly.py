"""debt j1-legacy-record-actionability：历史导入申请凭据面 422 修复（只读合成卡延伸）.

根因：credential.query / credential.issue 都先取 delivery.find_by_request_id；历史导入申请
（M0 一次性迁移，payload 带 ``kind``）无运行时 delivery 实体 → 返回 None → handler 抛
NotFoundError → REST 映射 HTTP 422。但该申请作为**只读合成卡**确实存在（record_to_request
投影）。

修法（乔布斯拍板，执行既有宪法 D11/D47/D56，无需新 D-编号）：
- 历史导入申请 = 只读迁移记录；凭据面读路径不再 422，返回诚实空态
  status="not_issued" + legacy_import=True + 历史导入文案（不捏造 delivery / grant / 凭据）。
- 运行时签发（credential.issue）对历史导入是无效状态转换 → 诚实 InvalidStateError（非 422），
  不半截落库；前端按「无权/不可动作 = 不可见」隐藏「重新签发」入口。

真实在产单（运行时卡，payload 无 ``kind``，有 delivery）凭据流保持原行为不变。
"""

from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import InvalidStateError
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


@pytest.fixture()
def brain():
    """干净隔离 PG 克隆库（无 seed）+ BrainService，供注入历史导入申请而无 delivery."""
    ensure_runtime_schema()

    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    yield BrainService(state_store=ss)


def _inject_legacy_import_application(brain, request_id: str, *, status: str = "granted") -> None:
    """注入一个历史导入申请（payload 带 ``kind`` → 只读合成卡判定），**不**建 delivery_task.

    模拟 M0 一次性迁移：申请记录在 application_record，但无运行时交付实体图。
    """
    store = brain._state_store.database_store
    store.application_repo.upsert_from_request(
        {
            "id": request_id,
            "kind": "apply",  # legacy 导入判别位（is_runtime_request_payload → False）
            "source_ref": f"legacy:data_apply:{request_id}",
            "status": status,
            "applicant": "张三（脱敏）",
            "applicantDept": "某区县某局",
            "resourceId": "res-legacy-x",
            "resourceName": "历史导入资源",
            "purpose": "历史迁移导入申请",
        },
        tenant_id=TENANT,
    )


def _invoke(brain, skill_id: str, payload: dict, *, role: str = "ROLE_ORGAN_OPERATER") -> dict:
    out = invoke_trusted(brain, skill_id, payload, role=role)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


# ──────────────────────────────────────────────────────────────────────
# credential.query：历史导入申请不再 422，返回诚实只读空态
# ──────────────────────────────────────────────────────────────────────


def test_credential_query_legacy_import_returns_not_issued_not_422(brain):
    """历史导入申请（无 delivery）查凭据 → not_issued + legacy_import，不抛 NotFoundError(422)."""
    _inject_legacy_import_application(brain, "LEGACY-CRED-1")
    result = _invoke(brain, "credential.query", {"request_id": "LEGACY-CRED-1"})
    assert result["credential"] is None
    assert result["status"] == "not_issued"
    assert result.get("legacy_import") is True, "须标 legacy_import 供前端隐藏运行时入口"
    # 诚实文案：历史导入 + 未签发，不臆造凭据/交付
    assert "历史导入" in result.get("hint", "")
    # 不捏造任何凭据前缀
    assert "AK-DEMO" not in str(result)
    assert "AK-SELF" not in str(result)


def test_credential_sample_render_legacy_import_not_issued_not_422(brain):
    """sample.render 对历史导入申请也走诚实空态，不渲染样例、不 422."""
    _inject_legacy_import_application(brain, "LEGACY-CRED-2")
    out = _invoke(brain, "credential.sample.render", {"request_id": "LEGACY-CRED-2"})
    assert out["status"] == "not_issued"
    assert out["samples"] is None


# ──────────────────────────────────────────────────────────────────────
# credential.issue：历史导入是只读迁移记录，运行时签发是无效状态转换
# ──────────────────────────────────────────────────────────────────────


def test_credential_issue_legacy_import_rejected_as_invalid_state(brain):
    """对历史导入申请签发凭据 → 诚实 InvalidStateError（非 422 NotFoundError），不半截落库."""
    _inject_legacy_import_application(brain, "LEGACY-CRED-3")
    with pytest.raises(InvalidStateError) as exc:
        _invoke(
            brain,
            "credential.issue",
            {"request_id": "LEGACY-CRED-3", "confirmed": True},
            role="ROLE_ORGAN_MANAGER",
        )
    assert "历史导入" in str(exc.value)


# ──────────────────────────────────────────────────────────────────────
# 真正不存在的申请：仍诚实报 NotFoundError（不被本修复吞掉）
# ──────────────────────────────────────────────────────────────────────


def test_credential_query_truly_absent_request_still_not_found(brain):
    from zw_brain.command.brain import NotFoundError

    with pytest.raises(NotFoundError):
        _invoke(brain, "credential.query", {"request_id": "DOES-NOT-EXIST-AT-ALL"})


# ──────────────────────────────────────────────────────────────────────
# 投影：历史导入申请卡带 isLegacyImport 标识（供前端隐藏运行时专属动作入口）
# key 与前端 P3RequestDetail / 快照卡单一契约统一为 isLegacyImport（旧名 legacyImport 已退役）。
# ──────────────────────────────────────────────────────────────────────


def test_request_projection_flags_legacy_import(brain):
    """record_to_request 投影对历史导入单标 isLegacyImport=True；运行时单（无 kind）不标."""
    _inject_legacy_import_application(brain, "LEGACY-CRED-4", status="apply")
    req = brain.get_request("LEGACY-CRED-4")
    assert req.get("isLegacyImport") is True

