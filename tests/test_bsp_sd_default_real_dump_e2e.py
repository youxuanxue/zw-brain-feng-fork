"""阶段 F — R-401 修复：sd-default 端到端 真实数据 验证（上接 IAF + 下接 role policy）。

输入：
  - `old/10示例数据/dump-dsp_bsp-202604271139.sql` 真实脱敏 BSP dump（710 用户 / 4187 user_role /
    3633 role_resource）
  - `tests/fixtures/m0-sd-default/{iaf-binding,role-mapping,capability-mapping}-manifest.json`
    M0 实施 baseline manifest

验证链路：
  1. GovernanceMapper.import_dump 把 dump+manifests 写入 sd-default canonical：
     - actor_projection 710 行（status="active" 的占多数；isolated user 留 iam_account_missing）
     - actor_org_role_binding > 0（pub_user_organ_role × # 拆分 × role mapping）
     - legacy_policy_mapping_candidate > 0（pub_role_resource × capability mapping）
  2. tenant.policy.evaluate 一开始 deny（missing_tenant_policy）
  3. governance.policy_candidate.review (decision=approve_and_apply) 落 tenant_capability_policy
  4. tenant.policy.evaluate 再调返回 allowed=True（"下接 role policy" 闭环）
  5. 真实 actor_snapshot（iaf_sub-bound）查询时角色 binding 走 actor_org_role_binding（"上接 IAF" 闭环）

定位：本测试是 M0 现场切换的回归基线；fixture 内容是 团队协作下 M0 实施工程师工作产物 baseline，
现场可调整后回流。脚本 `scripts/build_m0_sd_default_fixtures.py` 是 fixture 生成器，幂等可复跑。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DUMP = REPO_ROOT / "old/10示例数据/dump-dsp_bsp-202604271139.sql"
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/m0-sd-default"

# 让 fixture 生成器函数可以被 import
sys.path.insert(0, str(REPO_ROOT / "scripts"))


_TEST_SUB_PREFIX = "IAM-TEST-"


def _simulate_iam_backfill(iaf_entries: list[dict]) -> list[dict]:
    """模拟 ingest_iam_sub_backfill 跑完后的 fixture 形态：iaf-sd-<sha1> 占位 → IAM-TEST-<sha1>。

    P0-B 后 mapper 把 `iaf-sd-` 前缀归一化为空（fail-closed 触发 iam_account_missing），
    fixture baseline 仍持占位（IAM 未注入前的原始形态）。e2e 在加载时模拟"IAM 团队已注入"。
    单独的 fail-closed 测试 test_sd_default_real_dump_fail_closed_on_placeholder_sub 保留
    占位形态验证 mapper 守卫生效。
    """
    out: list[dict] = []
    for entry in iaf_entries:
        copy = dict(entry)
        sub = str(copy.get("iaf_sub") or "")
        if sub.startswith("iaf-sd-"):
            copy["iaf_sub"] = _TEST_SUB_PREFIX + sub[len("iaf-sd-"):]
        out.append(copy)
    return out


def _load_manifest_sql(*, simulate_backfill: bool = True) -> str:
    """读 3 张 JSON manifest，转为 MySQL CREATE/INSERT 块。

    simulate_backfill=True（默认）：模拟 IAM 注入回填，iaf-sd- 占位 → IAM-TEST-；
    simulate_backfill=False：保留占位形态，给 fail-closed 回归测试用。
    """
    from build_m0_sd_default_fixtures import manifest_sql_for_test

    iaf = json.loads((FIXTURE_DIR / "iaf-binding-manifest.json").read_text(encoding="utf-8"))["entries"]
    if simulate_backfill:
        iaf = _simulate_iam_backfill(iaf)
    role = json.loads((FIXTURE_DIR / "role-mapping-manifest.json").read_text(encoding="utf-8"))["rows"]
    capability = json.loads(
        (FIXTURE_DIR / "capability-mapping-manifest.json").read_text(encoding="utf-8")
    )["rows"]
    return manifest_sql_for_test(iaf, role, capability)


def _prepare_merged_dump(tmp: Path) -> Path:
    dump_dir = tmp / "dumps"
    dump_dir.mkdir(parents=True, exist_ok=True)
    # mapper 用 `schema_from_dump_name` 解析 dump filename → schema；保持 "dsp_bsp" 前缀。
    merged = dump_dir / "dump-dsp_bsp-202604271139-sd-default-m0.sql"
    merged.write_text(
        REAL_DUMP.read_text(encoding="utf-8") + "\n\n" + _load_manifest_sql(),
        encoding="utf-8",
    )
    return merged


def _bootstrap_service(tmp: Path) -> tuple[Any, Any]:
    from zw_brain.command.brain import BrainService
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema
    from zw_brain.shared.state_store import StateStore

    os.environ["ZW_BRAIN_DB_PATH"] = str(tmp / "sd_default.db")
    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    return (
        BrainService(state_store=StateStore(database_store=database_store)),
        GovernanceProjectionRepository(),
    )


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_sd_default_real_dump_iaf_to_role_policy_e2e() -> None:
    """完整 M0 链路：真实 dump + manifest → projection → candidate → review → tenant policy → 允许调用。"""
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper
    from zw_brain.domain.policy import ACTOR_NAMES

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        service, gov = _bootstrap_service(tmp)
        dump = _prepare_merged_dump(tmp)

        # ---- 1. apply 导入 ----
        stats = GovernanceMapper().import_dump(dump, dry_run=False)
        report = stats.to_dict()
        assert report["mode"] == "apply"

        # 710 pub_user 入 source_counts（防 R-301 类双计回归）
        assert report["source_counts"]["pub_user"] == 710, report["source_counts"]

        # ---- 2. actor_projection 上接 IAF ----
        actors = gov.list_actors(tenant_id="sd-default")
        assert len(actors) == 710, f"应导入 710 actor，实得 {len(actors)}"

        # synthetic iaf_sub 命中：e2e 在 fixture 加载时模拟 IAM 注入回填（_simulate_iam_backfill），
        # 把 iaf-sd-<sha1> 占位换成 IAM-TEST-<sha1>。P0-B 后 mapper 把 iaf-sd- 前缀归一化为空
        # （fail-closed），baseline fixture 仍持占位 — 见 test_sd_default_real_dump_fail_closed_on_placeholder_sub
        bound = [a for a in actors if a.external_actor_id.startswith(_TEST_SUB_PREFIX)]
        assert len(bound) > 600, (
            f"应有 >600 actor 通过 iaf_binding_manifest 拿到 iaf_sub，实得 {len(bound)}/{len(actors)}"
        )
        # 至少一个 active（说明 mapper 走完了 active path 不止 iam_account_missing）
        active = [a for a in bound if a.status == "active"]
        assert active, "应至少有 1 active actor（pub_user_organ_role 命中 + role_mapping 命中）"

        # ---- 3. actor_org_role_binding：多组织 / 多角色拆分（'#' 分隔）的硬路径 ----
        bindings = gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active")
        assert bindings, "应有 active binding（pub_user_organ_role 136 行 × # 拆分 × role mapping 命中）"
        # 所有 binding 的 role_code 必须在产品 6 角色内（fail-closed 已防 legacy 漏入）
        unknown_roles = {b.role_code for b in bindings} - set(ACTOR_NAMES.keys())
        assert not unknown_roles, f"binding 不应含 legacy/技术角色：{unknown_roles}"
        # 至少存在过 '#' 拆分产生的多角色 user
        actor_to_roles: dict[str, set[str]] = {}
        for b in bindings:
            actor_to_roles.setdefault(b.external_actor_id, set()).add(b.role_code)
        multi_role_actors = [aid for aid, rs in actor_to_roles.items() if len(rs) >= 2]
        # 真实 dump 有 'ROLE_DATA_LEADER#ROLE_MGMT_LEADER' 类多角色串：拆分后某 actor 应同时挂 2+ 角色。
        assert multi_role_actors, "应至少有 1 actor 经 # 拆分获得 2+ 角色 binding（防多角色拆分回归）"

        # ---- 4. legacy_policy_mapping_candidate 下接 role policy ----
        candidates = gov.list_policy_candidates(tenant_id="sd-default")
        assert candidates, "应有 pub_role_resource × capability_mapping 命中的 candidate"
        # 抽一个 capability_id 命中真实注册 Skill 且 legacy_role_ref 映射出产品角色的 candidate
        appliable = [
            c
            for c in candidates
            if c.candidate_status == "pending_review"
            and c.capability_id in {"catalog.entry.query", "audit.list", "resource.asset.query", "request.list", "catalog.browse"}
            and str(c.legacy_role_ref or "") in ACTOR_NAMES
        ]
        assert appliable, "应至少有 1 candidate 同时命中：capability ∈ 注册集 & legacy_role_ref 映射到产品角色"

        sample = appliable[0]
        chosen_role = str(sample.legacy_role_ref)

        # ---- 5. tenant.policy.evaluate 起点：deny ----
        actor_snapshot = {
            "subject": next(a.external_actor_id for a in active),
            "tenant_id": "sd-default",
            "org_code": active[0].org_code or "",
            "status": "active",
            "role_codes": [chosen_role],
        }
        denied = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": sample.capability_id,
                "surface": sample.surface or "webui",
                "role": chosen_role,
                "actor_snapshot": actor_snapshot,
            },
        )
        assert denied["allowed"] is False
        assert denied["decision_reason"] == "missing_tenant_policy"

        # ---- 6. approve_and_apply 落 tenant_capability_policy ----
        reviewed = service.invoke_skill(
            "governance.policy_candidate.review",
            {
                "decision": "approve_and_apply",
                "items": [
                    {
                        "legacy_permission_ref": sample.legacy_permission_ref,
                        "capability_id": sample.capability_id,
                        "legacy_system": sample.legacy_system,
                    }
                ],
                # D55/P4：身份治理收归平台运维员（governance.policy_candidate.review={ROLE_SYSTEM}）。
                # permission-matrix-0610 清残留：原 BUSIAUDIT 自 wave1 起 403、本测试 pre-existing 失败。
                "role": "ROLE_SYSTEM",
                "confirmed": True,
            },
        )
        assert reviewed["audit_id"]
        assert reviewed["result"]["summary"]["applied_policy_count"] == 1

        # ---- 7. tenant.policy.evaluate 终点：allowed=True（"下接 role policy" 链路闭合）----
        allowed = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": sample.capability_id,
                "surface": sample.surface or "webui",
                "role": chosen_role,
                "actor_snapshot": actor_snapshot,
            },
        )
        assert allowed["allowed"] is True, allowed
        assert allowed["source"] == "tenant_capability_policy"


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_sd_default_real_dump_fail_closed_without_manifest() -> None:
    """对照实验：缺 manifest 时（即手上有真实 dump 但还没拿到 M0 实施 baseline）必须 fail-closed —
    candidate / binding 都不应写入，否则 R-004 fail-closed 设计回归。"""
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _bootstrap_service(tmp)
        dump_dir = tmp / "dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        merged = dump_dir / "dump-dsp_bsp-202604271139-no-manifest.sql"
        # 复制 dump，不附 manifest
        merged.write_text(REAL_DUMP.read_text(encoding="utf-8"), encoding="utf-8")

        stats = GovernanceMapper().import_dump(merged, dry_run=False)
        report = stats.to_dict()
        gov = GovernanceProjectionRepository()

        # actor_org_role_binding 应为 0（无 iaf_binding_manifest → 无 iaf_sub → 全员 iam_account_missing → 不写 binding）
        bindings = gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active")
        assert not bindings, f"无 manifest 时不应有 binding 写入，实得 {len(bindings)}"

        # legacy_policy_mapping_candidate 应为 0（无 capability_mapping_manifest）
        cands = gov.list_policy_candidates(tenant_id="sd-default")
        assert not cands, f"无 manifest 时不应有 candidate 写入，实得 {len(cands)}"

        # 必须 emit `missing_manifest` issue（fail-closed 标记）
        missing_manifest_issues = [i for i in report["issues"] if i["type"] == "missing_manifest"]
        assert missing_manifest_issues, "缺 manifest 时必须 emit missing_manifest issue"


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_sd_default_real_dump_fail_closed_on_placeholder_sub() -> None:
    """P0-B 回归：fixture iaf-sd-* 占位 sub 进 mapper 必须 fail-closed（iam_account_missing
    + 0 active binding），不能写入 actor_projection 业务字段或 binding。

    设计意图：占位 sub 是 build_m0_sd_default_fixtures.py 生成的合成 hash，永远不可能
    通过真实 IAF OIDC 验签。如果允许占位 sub 进 canonical：
      - actor_projection.external_actor_id = iaf-sd-<sha1> 污染数据
      - 真实用户登录时 IAF 给的真 sub 不匹配，找不到投影 → 二次写一份新 actor，孤儿数据
    所以 mapper 必须把占位前缀视同未注入。
    """
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _bootstrap_service(tmp)
        dump_dir = tmp / "dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        merged = dump_dir / "dump-dsp_bsp-202604271139-placeholder-sub.sql"
        # 关键：simulate_backfill=False 保留 iaf-sd-* 占位形态
        merged.write_text(
            REAL_DUMP.read_text(encoding="utf-8") + "\n\n" + _load_manifest_sql(simulate_backfill=False),
            encoding="utf-8",
        )

        stats = GovernanceMapper().import_dump(merged, dry_run=False)
        report = stats.to_dict()
        gov = GovernanceProjectionRepository()

        # 全 710 actor 必须 fail-closed 为 iam_account_missing（manifest 全是占位，mapper 归一化为空）
        actors = gov.list_actors(tenant_id="sd-default")
        assert len(actors) == 710, f"actor 行数应仍为 710 (留 evidence)，实得 {len(actors)}"
        missing = [a for a in actors if a.status == "iam_account_missing"]
        assert len(missing) == 710, (
            f"占位 sub 全员应 fail-closed 为 iam_account_missing，实得 {len(missing)}/{len(actors)}"
        )

        # 必须有 iam_account_missing issue（不是默默接受占位）
        missing_issues = [i for i in report["issues"] if i["type"] == "iam_account_missing"]
        assert missing_issues, "占位 sub 进 mapper 必须 emit iam_account_missing issue"

        # 不能写任何 active binding（占位 sub 不应触发 binding 路径）
        bindings = gov.list_actor_org_role_bindings(tenant_id="sd-default", binding_status="active")
        assert not bindings, f"占位 sub 不应写 binding，实得 {len(bindings)}"

        # 不能有任何 actor 的 external_actor_id 以 iaf-sd- 开头（mapper 归一化生效）
        leaked = [a for a in actors if a.external_actor_id.startswith("iaf-sd-")]
        assert not leaked, f"占位 sub 不应进 external_actor_id，实得 {len(leaked)} 条泄漏"
