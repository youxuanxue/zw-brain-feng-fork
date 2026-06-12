#!/usr/bin/env python3
"""权限矩阵上帝视角机械审计（permission-matrix-0610）。

对照业务方权威尺子（重构平台权限梳理-0609.docx + 平台系统角色菜单梳理v5.xlsx，
经 D55 裁决落账为 old/问题反馈/权限梳理-0609-修复任务目标清单.md §四 目标矩阵），
diff 权限四副本 + 测试镜像，输出每项四档判定：

  aligned                — 与目标一致
  backed-by-ruling       — 与 v5 字面不同但有签字裁决背书（D50/D53/D54/D55 注释锚点）
  conflict               — 与裁决/目标矛盾，须修复

第四档 needs-business-decision（文档未覆盖且无裁决背书 → 记债不猜）由审计人产生：
conflict 项若核查后既回不到 v5 也无裁决可引，就从 CAP_TARGET/BACKED_BY_RULING 摘出、
按 docs/preflight-debt.md 四段式记问题——脚本不替业务方猜答案，故无自动判定路径。

读取面（全只读）：
  1. zw_brain/domain/policy.py            PERMISSION_ROLES（后端真闸，权威源）
  2. zw-brain-web/src/lib/pageAccess.ts   ACTION_ROLE_GATES + ROUTE_ROLE_OVERRIDES
  3. zw-brain-web/src/config/productShellNav.ts  shell 导航角色门
  4. zw_brain/domain/web_snapshot_redaction.py   快照裁剪 frozensets
  5. zw-brain-web/src/lib/requestFlowRoles.ts    前端角色常量
  6. tests/test_page_access.py            _SHELL_ROLES Python 测试镜像（漂移检测）
  7. zw_brain/capability_registry/registered/*.json  manifest product_scope.status

用法：.venv/bin/python scripts/audit_permission_matrix.py
退出码：0 = 无 conflict；1 = 存在 conflict。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zw_brain.domain import policy  # noqa: E402
from zw_brain.domain import web_snapshot_redaction as redaction  # noqa: E402
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES as _BIZ_CODES  # noqa: E402

BUSINESS_ROLE_CODES = frozenset(_BIZ_CODES)

OP = "ROLE_ORGAN_OPERATER"
MGR = "ROLE_ORGAN_MANAGER"
BUSI = "ROLE_BUSIAUDIT"
SEC = "ROLE_SECURITY_AUDIT"
SYS = "ROLE_SYSTEM"

# ---------------------------------------------------------------------------
# 目标矩阵（导航 10 壳 × 角色）—— 源自 v5 + D55 §四（清单），独立 oracle，
# 刻意不 import productShellNav，避免「自己对自己」同义反复。
# ---------------------------------------------------------------------------
NAV_TARGET: dict[str, tuple[frozenset[str], str]] = {
    "workbench": (frozenset({OP, MGR, BUSI, SEC, SYS}), "全角色工作台"),
    "discovery": (frozenset({OP, MGR, BUSI}), "D55/P17 审计员退找数据；P5 运营员仅浏览"),
    "request-flow": (frozenset({OP, MGR, BUSI}), "D55/P7·P21 运营员承受理 + 决策A"),
    "delivery-exchange": (frozenset({OP, MGR}), "D55/P13 反转F1 + P18 审计员退出"),
    "provider": (frozenset({OP, MGR, BUSI}), "v5 供数三岗位"),
    "compliance-ops": (frozenset({BUSI, SEC}), "D55/P8·P9 审计日志收窄"),
    "service-ops": (frozenset({BUSI, SYS}), "D57⑥ 管理员+审计员退全局服务调用监控（v5 服务调用日志口径）"),
    "integration-admin": (frozenset({SYS}), "D55/P2 外部系统收归运维员"),
    "engines": (frozenset({SYS}), "D55/P3 反转D49 流程表单配置归运维员"),
    "iam-governance": (frozenset({SYS}), "D55/P4 身份治理收归运维员"),
}

# ---------------------------------------------------------------------------
# 能力级目标点检表（D55 裁决敏感子集；存储口径——MANAGER 经 hierarchy 继承
# OPERATER 权限，目标写法与 policy.py 存储口径一致）。
# ---------------------------------------------------------------------------
CAP_TARGET: dict[str, tuple[frozenset[str], str]] = {
    # P1 运营员退供数维护
    "catalog.manage_entry.execute": (frozenset({OP}), "D55/P1"),
    "resource.manage_asset.execute": (frozenset({OP}), "D55/P1"),
    # P2 外部系统收归运维员（cascade.* manifest deferred:wave-3，防回潮照 G2 先例）
    "adapter.cascade.consume.execute": (frozenset({SYS}), "D55/P2+P22"),
    "adapter.cascade.replay.execute": (frozenset({SYS}), "D55/P2+P22"),
    "adapter.cascade.health.query.execute": (frozenset({SYS}), "D55/P2"),
    "adapter.external.mapping.query.execute": (frozenset({SYS}), "D55/P2"),
    # P3 流程表单配置归运维员（消费侧 suggest 不迁）
    "approval_flow.schema.commit.execute": (frozenset({SYS}), "D55/P3"),
    "form_schema.commit.execute": (frozenset({SYS}), "D55/P3"),
    "recommendation.rule.commit.execute": (frozenset({SYS}), "D55/P3"),
    "recommendation.similar_catalog.suggest.execute": (frozenset({OP, MGR, BUSI}), "D55/P3 消费侧"),
    # P4 身份治理归运维员
    "governance.iam_overview.execute": (frozenset({SYS}), "D55/P4"),
    "governance.policy_candidate.list.execute": (frozenset({SYS}), "D55/P4"),
    "governance.policy_candidate.review.execute": (frozenset({SYS}), "D55/P4"),
    # P8/P9 审计日志收窄
    "audit.list.execute": (frozenset({BUSI, SEC}), "D55/P8·P9"),
    "audit.replay_evidence_chain.execute": (frozenset({BUSI, SEC}), "D55/P8·P9"),
    "audit.event.query.execute": (frozenset({BUSI, SEC}), "D55/P8·P9"),
    # D57⑥：审计员退两面；管理员退全局 report 面，invocation.query 保留 MANAGER =
    # 「自家资源被调用情况」唯一读面在 P4Credential 凭据门内（裁决六明文保留）。
    "ops.service.invocation.query.execute": (frozenset({MGR, BUSI, SYS}), "D57⑥ + P4 凭据门窄读面"),
    "ops.service.report.query.execute": (frozenset({BUSI, SYS}), "D57⑥"),
    # P13/P18/#240 领数据
    "delivery.list.execute": (frozenset({OP, MGR}), "D55/P13+P18"),
    "delivery.view.execute": (frozenset({OP, MGR}), "D55/P13+P18"),
    "delivery.subscription.manage.execute": (frozenset({OP, MGR}), "D55/P13"),
    "subscription.terminate.execute": (frozenset({OP, MGR}), "D55/P13"),
    "delivery.reconcile_receipt.execute": (frozenset({OP, MGR}), "PR#240 D53⑥"),
    "delivery.file.download.execute": (frozenset({OP, MGR}), "PR#240 D53⑥"),
    "credential.query.execute": (frozenset({OP, MGR, BUSI}), "D55/P18"),
    # P17 审计员退找数据
    "data.search.execute": (frozenset({OP, MGR, BUSI}), "D55/P17"),
    "search.intent.parse.execute": (frozenset({OP, MGR, BUSI}), "D55/P17"),
    "catalog.resource_view.execute": (frozenset({OP, MGR, BUSI}), "D55/P17"),
    "catalog.resource.list.execute": (frozenset({OP, MGR, BUSI}), "D55/P17"),
    # P21 受理两级（dept_approve 含 OPERATER = resubmit 补件共用 key，deliberate）
    "application.resource.review.execute": (frozenset({BUSI}), "D55/P21"),
    "application.platform_approve.execute": (frozenset({BUSI}), "D55/P21"),
    "application.dept_approve.execute": (frozenset({MGR, OP}), "D55/P21 + resubmit 共 key"),
    # P22/P23 审计员只读 + 工单归运维员
    "ops.ticket.create.execute": (frozenset({SYS}), "D55/P23"),
    "ops.ticket.close.execute": (frozenset({SYS}), "D55/P23"),
    "ops.shift_handover.submit.execute": (frozenset({SYS}), "D55/P23"),
    "system.toggle_outage.execute": (frozenset({SYS}), "D55/P22"),
    "metadata.lineage.upsert.execute": (frozenset({OP}), "D55/P22③"),
    "ops.catalog.quality.upsert.execute": (frozenset({OP}), "D55/P22③"),
    # P7 运营员退申请人身份；D57④ 管理员申请人身份照 v5 保留（显式登记，收口前后端劈叉）
    "request.create.execute": (frozenset({OP, MGR}), "D55/P7 + D57④"),
    "request.submit.execute": (frozenset({OP, MGR}), "D55/P7 + D57④"),
    "demand.register.execute": (frozenset({OP, MGR}), "D55/P7"),
    "objection.case.create.execute": (frozenset({OP, MGR}), "D55/P7"),
    "application.draft.suggest.execute": (frozenset({OP, MGR}), "PR#240 P7"),
    # P11/P14 供数增权
    "catalog.entry.create.execute": (frozenset({OP}), "D55/P11（MGR 经 hierarchy）"),
    "catalog.entry.reverse_draft.create.execute": (frozenset({OP, MGR}), "D55/P14"),
    "catalog.entry.reverse_draft.suggest.execute": (frozenset({OP, MGR}), "D55/P14 + D57⑧ 死读权回收（0611 收尾：唯一消费面=向导，BUSIAUDIT 退 draft 审后无 UI 面）"),
    # D57⑧ 反向编目审核两级管线：部门审（confirm/reject）= 部门管理员；平台审汇入
    # catalog.entry.review（pending_platform_review + BUSIAUDIT）。拒下放操作员。
    "catalog.entry.reverse_draft.confirm.execute": (frozenset({MGR}), "D57⑧ 部门审"),
    "catalog.entry.reverse_draft.reject.execute": (frozenset({MGR}), "D57⑧ 部门审"),
    # G1 挂接审核照 v5
    "resource.asset.review.execute": (frozenset({MGR}), "D55/G1"),
    # D57⑤ 发布权回收仅业务运营员（目录 + 资源同口径，严格 v5）
    "catalog.entry.publish.execute": (frozenset({BUSI}), "D57⑤"),
    "resource.asset.publish.execute": (frozenset({BUSI}), "D57⑤ 机械延伸"),
    # D54 GATE-1 代理服务注册角色
    "resource.api.register.execute": (frozenset({OP, MGR}), "D54/GATE-1"),
    "resource.api.submit_review.execute": (frozenset({OP, MGR}), "D54/GATE-1"),
    "resource.api.review.execute": (frozenset({MGR}), "D54/GATE-1"),
    "resource.api.publish.execute": (frozenset({MGR}), "D54/GATE-1"),
    # G6 异议核查 = 运营员 + 管理员
    "objection.case.accept.execute": (frozenset({MGR, BUSI}), "D55/G6"),
    "objection.case.close.execute": (frozenset({MGR, BUSI}), "D55/G6"),
}

# 与 v5 字面有出入但有签字裁决/立项背书的集合（防误报；basis 必须可追溯）
BACKED_BY_RULING: dict[str, str] = {
    "adapter.national.catalog.pull.execute": "D50 国家通道立项 {MGR,BUSI}",
    "adapter.national.application.submit.execute": "D50",
    "catalog.national_ext_elem.compile.execute": "D50/C5",
    "application.escalate_national.execute": "D50/C6",
    "application.grant.revoke.execute": "j1-credential-revoke 决策A {BUSI,OP}",
    "application.grant.suspend.execute": "j1-credential-revoke 决策A {BUSI}",
    "quality.rule.upsert.execute": "D27#14 旁路（v5 检测规则=运维员，但本面非 v5 质量检测复刻）",
    "tenant.policy.evaluate.execute": "只读策略评估（D55/P4 仅收 BUSIAUDIT；MGR/SEC 只读保留）",
}

WRITE_TOKENS = {
    "create", "update", "upsert", "delete", "submit", "approve", "decide",
    "publish", "withdraw", "revoke", "suspend", "terminate", "issue",
    "ingest", "sync", "import", "configure", "assign", "accept", "reject",
    "reply", "escalate", "close", "commit", "advance", "confirm", "run",
    "anchor", "toggle", "grant", "register", "bind", "rollback", "enable",
    "disable", "dispatch", "handoff", "start", "stop", "attach", "renew",
    "consume", "manage", "prepare", "claim", "review",
}

ROLE_RE = re.compile(r"'(ROLE_[A-Z_]+)'")


def parse_shell_nav() -> dict[str, frozenset[str]]:
    src = (REPO / "zw-brain-web/src/config/productShellNav.ts").read_text(encoding="utf-8")
    shells: dict[str, frozenset[str]] = {}
    for m in re.finditer(r"key:\s*'([^']+)'.*?roles:\s*\[([^\]]+)\]", src, re.DOTALL):
        shells[m.group(1)] = frozenset(ROLE_RE.findall(m.group(2)))
    return shells


def parse_action_gates() -> dict[str, frozenset[str]]:
    src = (REPO / "zw-brain-web/src/lib/pageAccess.ts").read_text(encoding="utf-8")
    m = re.search(r"ACTION_ROLE_GATES\b[^=]*=\s*\{(.*?)\n\};", src, re.DOTALL)
    assert m, "pageAccess.ts 缺 ACTION_ROLE_GATES"
    gates: dict[str, frozenset[str]] = {}
    for line in m.group(1).splitlines():
        em = re.match(r"\s*'([^']+)'\s*:\s*\[([^\]]+)\]", line)
        if em:
            gates[em.group(1)] = frozenset(ROLE_RE.findall(em.group(2)))
    return gates


def parse_test_mirror() -> dict[str, frozenset[str]]:
    src = (REPO / "tests/test_page_access.py").read_text(encoding="utf-8")
    m = re.search(r"_SHELL_ROLES[^=]*=\s*\{(.*?)\n\}", src, re.DOTALL)
    assert m, "tests/test_page_access.py 缺 _SHELL_ROLES"
    mirror: dict[str, frozenset[str]] = {}
    for em in re.finditer(r'"([a-z-]+)":\s*frozenset\(\s*\{([^}]*)\}', m.group(1)):
        roles = frozenset(re.findall(r'"(ROLE_[A-Z_]+)"', em.group(2)))
        mirror[em.group(1)] = roles
    return mirror


def manifest_statuses() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted((REPO / "zw_brain/capability_registry/registered").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d.get("slug", p.stem)] = (d.get("product_scope") or {}).get("status", "?")
    return out


def sweep_can_perform_action_ids() -> set[str]:
    ids: set[str] = set()
    for p in (REPO / "zw-brain-web/src").rglob("*"):
        if p.suffix not in {".vue", ".ts"} or p.name == "pageAccess.ts":
            continue
        for m in re.finditer(r"canPerformAction\(\s*'([^']+)'", p.read_text(encoding="utf-8")):
            ids.add(m.group(1))
    return ids


def sweep_hardcoded_role_arrays() -> list[str]:
    hits: list[str] = []
    for p in sorted((REPO / "zw-brain-web/src/pages").glob("*.vue")):
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\[\s*'ROLE_[A-Z_]+'\s*(,\s*'ROLE_[A-Z_]+'\s*)*\]", line):
                hits.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:120]}")
    return hits


def main() -> int:
    conflicts: list[str] = []
    backed: list[str] = []
    aligned = 0

    shells = parse_shell_nav()
    gates = parse_action_gates()
    mirror = parse_test_mirror()
    statuses = manifest_statuses()

    print("=" * 78)
    print("权限矩阵机械审计 permission-matrix-0610")
    print("=" * 78)

    # 1) 导航 10 壳 vs 目标
    print("\n[1] 导航壳 × 角色 vs 目标矩阵（v5/§四）")
    for key, (target, basis) in NAV_TARGET.items():
        cur = shells.get(key)
        if cur is None:
            conflicts.append(f"NAV {key}: productShellNav.ts 缺该壳（目标 {sorted(target)}，{basis}）")
        elif cur != target:
            conflicts.append(f"NAV {key}: 现 {sorted(cur)} ≠ 目标 {sorted(target)}（{basis}）")
        else:
            aligned += 1
    for key in shells:
        if key not in NAV_TARGET:
            conflicts.append(f"NAV {key}: 目标矩阵无此壳（幽灵导航？）")

    # 2) 测试镜像漂移：tests/test_page_access.py _SHELL_ROLES vs TS 真值
    print("[2] 测试镜像 _SHELL_ROLES vs productShellNav.ts")
    for key, ts_roles in shells.items():
        py_roles = mirror.get(key)
        if py_roles is None:
            conflicts.append(f"MIRROR {key}: tests/test_page_access.py _SHELL_ROLES 缺该键（TS 已有）")
        elif py_roles != ts_roles:
            conflicts.append(
                f"MIRROR {key}: 测试镜像 {sorted(py_roles)} ≠ TS 真值 {sorted(ts_roles)}（守卫弱化）"
            )
        else:
            aligned += 1
    for key in mirror:
        if key not in shells:
            conflicts.append(f"MIRROR {key}: 测试镜像有、TS 真值无（stale 键）")

    # 3) ACTION_ROLE_GATES vs 后端 policy set-equal
    print("[3] ACTION_ROLE_GATES vs policy.PERMISSION_ROLES")
    for action, fe_roles in gates.items():
        be = policy.PERMISSION_ROLES.get(f"{action}.execute")
        if be is None:
            conflicts.append(f"GATE {action}: 后端 policy 无对应 key")
        elif frozenset(be) != fe_roles:
            conflicts.append(f"GATE {action}: 前端 {sorted(fe_roles)} ≠ 后端 {sorted(be)}")
        else:
            aligned += 1

    # 4) canPerformAction 字面量必须已注册（未注册默认放行 = 漏洞类）
    print("[4] canPerformAction 字面量注册 sweep")
    for action in sorted(sweep_can_perform_action_ids()):
        if action not in gates:
            conflicts.append(f"UNREGISTERED canPerformAction('{action}')：未注册默认放行")
        else:
            aligned += 1

    # 5) pages 禁硬编码角色数组
    print("[5] src/pages/*.vue 硬编码角色数组 sweep")
    for hit in sweep_hardcoded_role_arrays():
        conflicts.append(f"HARDCODED {hit}")

    # 6) 能力级目标点检
    print("[6] 能力级目标点检（D55 裁决敏感子集）")
    for cap, (target, basis) in CAP_TARGET.items():
        cur = policy.PERMISSION_ROLES.get(cap)
        if cur is None:
            conflicts.append(f"CAP {cap}: policy 缺该能力（目标 {sorted(target)}，{basis}）")
        elif frozenset(cur) != target:
            conflicts.append(f"CAP {cap}: 现 {sorted(cur)} ≠ 目标 {sorted(target)}（{basis}）")
        else:
            aligned += 1

    # 7) 安全审计员零写权（docx「无任何写操作权限」）
    print("[7] 安全审计员零写权扫描（写动词启发 + 裁决豁免）")
    for cap, roles in sorted(policy.PERMISSION_ROLES.items()):
        if SEC not in roles:
            continue
        tokens = set(cap.replace(".execute", "").split("."))
        hit = tokens & WRITE_TOKENS
        if not hit:
            continue
        if cap in BACKED_BY_RULING:
            backed.append(f"SEC-WRITE {cap}（{BACKED_BY_RULING[cap]}）")
        else:
            conflicts.append(f"SEC-WRITE {cap}: 安全审计员持写动词能力 {sorted(hit)}（D55/P22 违例）")

    # 8) 退役角色防回潮
    print("[8] 退役角色防回潮（ROLE_SECURITY_ADMIN / 旧编号角色码）")
    for cap, roles in policy.PERMISSION_ROLES.items():
        bad = set(roles) - BUSINESS_ROLE_CODES - {"admin", "system"}
        if bad:
            conflicts.append(f"RETIRED {cap}: 含非法角色 {sorted(bad)}")
    for name in dir(redaction):
        val = getattr(redaction, name)
        if isinstance(val, frozenset) and val and all(isinstance(x, str) for x in val):
            bad = {x for x in val if x.startswith("ROLE_")} - BUSINESS_ROLE_CODES
            if bad:
                conflicts.append(f"RETIRED redaction.{name}: 含非法角色 {sorted(bad)}")

    # 9) 已落裁决背书项（信息性）
    for cap, basis in BACKED_BY_RULING.items():
        if cap in policy.PERMISSION_ROLES and f"SEC-WRITE {cap}" not in " ".join(backed):
            backed.append(f"{cap} = {sorted(policy.PERMISSION_ROLES[cap])}（{basis}）")

    # 报告
    print("\n" + "=" * 78)
    print(f"aligned 检查项: {aligned}")
    print(f"\nbacked-by-ruling ({len(backed)}):")
    for b in sorted(set(backed)):
        print(f"  ◦ {b}")
    print(f"\nconflict ({len(conflicts)}):")
    for c in conflicts:
        status_note = ""
        m = re.search(r"(adapter\.[a-z.]+)\.execute", c)
        if m and m.group(1) in statuses:
            status_note = f"  [manifest={statuses[m.group(1)]}]"
        print(f"  ✗ {c}{status_note}")
    print("=" * 78)
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
