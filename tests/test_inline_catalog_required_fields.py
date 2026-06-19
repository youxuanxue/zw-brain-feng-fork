# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: API (brain.invoke_skill 层)
# Roles: ROLE_ORGAN_OPERATER (编目员)
# Trace:
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j2-online-catalog-compile.feature
"""在线编制基本信息必填校验（0611 业务口径确认单 §A，薛娇 2026-06-12 确认）.

三向覆盖（任务口径）：
  1. 必填缺失拒 — 在线编制目录（经 catalog.entry.create_draft 新铸）缺必填项时
     submit_review 被拒，中文文案列出缺失字段名；
  2. 补全后过 — 必填补全（创建即全 / update 补全两条路径）→ pending_review；
  3. 存量豁免 — 存量导入形态目录（summary_json 无 data_catalog_code）不回溯校验，
     流转不受影响（fail-closed 误伤防护）。
  + 条件必填 — 共享类型=有条件共享(2) 时共享条件必填，其余共享类型选填。

口径单源：前端字典 zw-brain-web/src/lib/catalogCompileFields.ts BASIC_INFO_FIELDS；
后端镜像 zw_brain/command/handlers/j1/catalog_entry.py _INLINE_BASIC_REQUIRED_FIELDS。

数据隔离：本测试只新铸草稿目录（不读真实 seed），由根 conftest 的 function-scoped
空 PG 克隆（已 alembic upgrade head 建表）供给，跨测试天然隔离——无需真灌库 / shadow。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"


@pytest.fixture()
def brain():
    # function-scoped：根 conftest 每个测试克隆一个新空 PG 库并重置 engine/audit 全局，
    # 故 store + 审计 sink 必须每测试重建并对当前克隆库重新挂载（session 级会绑到已 DROP 的库）。
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


@pytest.fixture()
def catalog_repo():
    from zw_brain.domain.repositories.catalog import CatalogRepository

    return CatalogRepository()


def _code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _call(brain, skill: str, payload: dict) -> dict:
    role = str(payload.pop("role", "ROLE_ORGAN_OPERATER"))
    return invoke_trusted(brain, skill, payload, role=role)["result"]


def _full_basic_summary(**overrides) -> dict:
    """16 字段口径下的完整必填集（共享类型默认无条件共享，避免连带共享条件）。"""
    base = {
        "catalog_type": "民政服务",
        "source_system": "医疗救助建模系统",
        "domain": "社会保障",
        "application_scenario": "用于医疗救助资格审核",
        "resource_format": "0200",
        "business_update_cycle": "2",
        "data_update_cycle": "2",
        "shared_way": "api",
        "shared_type": "1",
        "open_type": "3",
        "description": "覆盖医疗救助申请人基础信息的目录",
    }
    base.update(overrides)
    return base


# ============================================================================
# 1. 必填缺失拒
# ============================================================================


def test_inline_submit_missing_required_rejected_with_chinese_detail(brain, catalog_repo):
    """负向 — 在线编制目录只填名称即提交 → 拒绝，文案列出缺失必填项；目录仍是草稿."""
    from zw_brain.command.brain import InvalidStateError

    code = _code("J2-REQ-MISS")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "必填缺失目录", "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    with pytest.raises(InvalidStateError) as exc_info:
        _call(brain, "catalog.entry.submit_review", {
            "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
        })
    message = str(exc_info.value)
    assert "基本信息未填全" in message
    for label in ("数据资源分类", "来源系统", "所属领域", "应用场景", "数据资源摘要"):
        assert label in message, f"缺失项 {label} 未出现在拒绝文案：{message}"
    # 选填项不得出现在缺失清单（#6 内部部门=选填）
    assert "内部部门" not in message
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "draft"


def test_inline_submit_partial_fill_lists_only_remaining(brain):
    """负向 — update 补了一部分 → 拒绝文案只列剩余缺失项."""
    from zw_brain.command.brain import InvalidStateError

    code = _code("J2-REQ-PART")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "部分补全目录", "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    partial = _full_basic_summary()
    partial.pop("description")
    partial.pop("domain")
    _call(brain, "catalog.entry.update", {
        "catalog_code": code, "title": "部分补全目录", "summary_json": partial,
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    with pytest.raises(InvalidStateError) as exc_info:
        _call(brain, "catalog.entry.submit_review", {
            "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
        })
    message = str(exc_info.value)
    assert "所属领域" in message
    assert "数据资源摘要" in message
    assert "来源系统" not in message  # 已补的不再出现


# ============================================================================
# 2. 补全后过（创建即全 / update 补全两条路径）
# ============================================================================


def test_inline_submit_complete_at_create_passes(brain, catalog_repo):
    """正向 — 创建草稿时基本信息即填全（字段嵌套在 summary_json["summary_json"]）→ 提交成功."""
    code = _code("J2-REQ-FULL-CREATE")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "创建即填全目录", "owner_org_id": "dept_a_test",
        "summary_json": _full_basic_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    submit = _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert submit["lifecycle_status"] == "pending_review"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "pending_review"


def test_inline_submit_complete_after_update_passes(brain, catalog_repo):
    """正向 — 创建时缺、update 补全（字段展开到 summary_json 顶层）→ 提交成功（向导真实序列）."""
    code = _code("J2-REQ-FULL-UPDATE")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "补全后提交目录", "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.update", {
        "catalog_code": code, "title": "补全后提交目录",
        "summary_json": _full_basic_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    submit = _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert submit["lifecycle_status"] == "pending_review"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "pending_review"


# ============================================================================
# 3. 条件必填 — 共享条件随共享类型联动
# ============================================================================


def test_inline_conditional_share_requires_condition(brain):
    """负向 — 共享类型=有条件共享(2) 且共享条件为空 → 拒绝并点名共享条件."""
    from zw_brain.command.brain import InvalidStateError

    code = _code("J2-REQ-COND")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "有条件共享缺条件目录", "owner_org_id": "dept_a_test",
        "summary_json": _full_basic_summary(shared_type="2"),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    with pytest.raises(InvalidStateError, match="共享条件"):
        _call(brain, "catalog.entry.submit_review", {
            "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
        })


def test_inline_conditional_share_with_condition_passes(brain):
    """正向 — 共享类型=有条件共享(2) 且共享条件已填 → 提交成功."""
    code = _code("J2-REQ-COND-OK")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "有条件共享带条件目录", "owner_org_id": "dept_a_test",
        "summary_json": _full_basic_summary(
            shared_type="2", shared_condition="按授权范围共享，需符合个人信息保护要求"
        ),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    submit = _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert submit["lifecycle_status"] == "pending_review"


def test_inline_unconditional_share_condition_optional(brain):
    """正向 — 共享类型=无条件共享(1) 时共享条件可空（#15 条件必填语义的另一半）."""
    code = _code("J2-REQ-UNCOND")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "无条件共享目录", "owner_org_id": "dept_a_test",
        "summary_json": _full_basic_summary(shared_type="1"),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    submit = _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert submit["lifecycle_status"] == "pending_review"


# ============================================================================
# 4. 存量豁免 — 导入形态目录不回溯
# ============================================================================


def test_legacy_shaped_entry_exempt_from_required_check(brain, catalog_repo):
    """正向 — 存量导入形态（summary_json 无 data_catalog_code、缺大量字段）提交不被新校验拦.

    存量目录非 create_draft 铸造（旧平台 adapter 导入），summary_json 顶层没有
    data_catalog_code 业务码——必填校验对其恒豁免，流转照旧（D53 口径：1222 条
    旧目录缺字段属历史事实，不回溯卡死）。注入走 repo.upsert（D56 测试惯例）。
    """
    code = _code("LEGACY-EXEMPT")
    catalog_repo.upsert_from_resource(
        {
            "id": code,
            "name": "存量导入形态目录（字段不全）",
            "status": "draft",
            "provider": "dept_a_test",
            "region_code": "370100",
            "legacy_object_ref": code,
            # 刻意只有极简字段，且无 data_catalog_code —— 模拟旧平台导入行形态
            "description": None,
        },
        tenant_id=TENANT,
    )
    submit = _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert submit["lifecycle_status"] == "pending_review"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "pending_review"


# ============================================================================
# 5. 前后端必填口径对齐 — 字典漂移即红（无生成物同步机制的机械兜底）
# ============================================================================

_TS_DICT = REPO_ROOT / "zw-brain-web" / "src" / "lib" / "catalogCompileFields.ts"
_TS_FIELD_RE = re.compile(r"\{\s*key:\s*'([^']+)',\s*label:\s*'([^']+)',\s*rule:\s*'([^']+)'\s*\}")


def test_frontend_backend_required_dict_aligned():
    """前端字典（口径权威 BASIC_INFO_FIELDS）与后端镜像 _INLINE_BASIC_REQUIRED_FIELDS 逐项相等.

    两表「必须同步」目前靠注释自觉——本测试把它机械化：任一侧单改键/中文名/必填位/
    条件码即红。title 与 共享条件 在后端函数体内单独校验，以源码字面断言兜底。
    """
    import inspect

    from zw_brain.command.handlers.j1 import catalog_entry as backend

    ts_text = _TS_DICT.read_text(encoding="utf-8")
    block = ts_text.split("BASIC_INFO_FIELDS: BasicInfoFieldSpec[] = [", 1)[1].split("];", 1)[0]
    fields = _TS_FIELD_RE.findall(block)
    assert len(fields) == 16, f"BASIC_INFO_FIELDS 解析到 {len(fields)} 条（预期 16 字段）——字典结构变了，同步更新解析与本测试"

    # 1) 无条件必填集：键 + 中文名 + 顺序完全相等（title 除外，后端单独校验）。
    frontend_required = tuple((key, label) for key, label, rule in fields if rule == "required" and key != "title")
    assert frontend_required == backend._INLINE_BASIC_REQUIRED_FIELDS

    # 2) title：前端必填；后端 _missing_inline_required_basic_fields 以同一中文名单独校验。
    backend_src = inspect.getsource(backend._missing_inline_required_basic_fields)
    (title_label,) = [label for key, label, rule in fields if key == "title" and rule == "required"]
    assert f'"{title_label}"' in backend_src  # 数据资源目录名称

    # 3) 条件必填位：前端唯一 requiredIfConditionalShare 字段 = shared_condition；后端同键同中文名。
    conditional = [(key, label) for key, label, rule in fields if rule == "requiredIfConditionalShare"]
    assert conditional == [("shared_condition", "共享条件")]
    assert '"shared_condition"' in backend_src and '"共享条件"' in backend_src

    # 4) 「有条件共享」码同值（共享条件转必填的触发档）。
    match = re.search(r"CONDITIONAL_SHARE_TYPE\s*=\s*'([^']+)'", ts_text)
    assert match is not None
    assert match.group(1) == backend._CONDITIONAL_SHARE_TYPE == "2"
