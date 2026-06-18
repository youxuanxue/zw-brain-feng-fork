#!/usr/bin/env python3
"""backfill_actor_bindings.py — D62 A4 一次性回填。

D62 把产品角色的事实源从「IAM token / actor_projection.role_codes_json 快照」收口到
`actor_org_role_binding`（bearer/MCP/CLI 与浏览器两门都改读 binding）。切换前，部分存量
actor 的角色只活在 role_codes_json（旧 token 派生 / 早期导入）而无对应 active binding——
若不回填，切换瞬间这些用户会失去角色（fail-closed 到无岗位）。

本脚本把「active 且 role_codes_json 非空、却缺少对应 active binding」的 actor，按其
org_code + 每个产品角色补建 active binding（复用 repo.assign_actor_role，幂等）。

- 默认 `--dry-run`，只报告不写盘；`--apply` 才落库。
- 缺 org_code 的 actor 无法建机构域 binding → 记 needs-human，不猜测。
- 幂等：已存在的 (actor, org, role) active binding 跳过；重复运行安全。

退出码：0 = 成功（dry-run 或 apply）；非 0 = apply 期抛错。
接入：M0 迁移批在 D62 授权收口上线时运行一次（务必先备份库）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant-id", default="sd-default", help="目标租户（默认 sd-default）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只报告不写盘（默认）")
    mode.add_argument("--apply", action="store_true", help="实际回填 binding")
    parser.add_argument("--db-url", default=None, help="覆盖 ZW_BRAIN_DATABASE_URL（可选）")
    parser.add_argument("--json-report", type=Path, default=None, help="把完整报告写到该 json 文件")
    args = parser.parse_args(argv)
    apply = bool(args.apply)

    import os

    if args.db_url:
        os.environ["ZW_BRAIN_DATABASE_URL"] = args.db_url

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from zw_brain.domain.policy import filter_product_role_codes
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository

    repo = GovernanceProjectionRepository()
    tenant = args.tenant_id

    planned: list[dict[str, str]] = []
    needs_human: list[dict[str, str]] = []
    for actor in repo.list_actors(tenant_id=tenant):
        if actor.status != "active":
            continue
        roles = filter_product_role_codes(list(actor.role_codes_json or []))
        if not roles:
            continue
        existing = {
            (b.org_code, b.role_code)
            for b in repo.list_actor_org_role_bindings(
                tenant_id=tenant, external_actor_id=actor.external_actor_id, binding_status="active"
            )
        }
        org = str(actor.org_code or "")
        for role in roles:
            if not org:
                needs_human.append({"external_actor_id": actor.external_actor_id, "role_code": role, "reason": "no_org_code"})
                continue
            if (org, role) not in existing:
                planned.append({"external_actor_id": actor.external_actor_id, "org_code": org, "role_code": role})

    created = 0
    errors: list[dict[str, str]] = []
    if apply:
        for plan in planned:
            try:
                repo.assign_actor_role(
                    external_actor_id=plan["external_actor_id"],
                    org_code=plan["org_code"],
                    role_code=plan["role_code"],
                    tenant_id=tenant,
                    granted_by="backfill:D62-A4",
                )
                created += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({**plan, "error": str(exc)})

    report = {
        "tenant_id": tenant,
        "mode": "apply" if apply else "dry-run",
        "planned": planned,
        "planned_count": len(planned),
        "created_count": created,
        "needs_human": needs_human,
        "errors": errors,
    }
    if args.json_report:
        args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[backfill] tenant={tenant} planned={len(planned)} needs_human={len(needs_human)} created={created} errors={len(errors)}", file=sys.stderr)
    if not apply and planned:
        print(f"[dry-run] {len(planned)} 条 binding 可回填；加 --apply 执行（务必先备份库）。", file=sys.stderr)
    if needs_human:
        print(f"[needs-human] {len(needs_human)} 个 (actor,role) 无 org_code，无法建机构域 binding —— 人工补 org 后处理。", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
