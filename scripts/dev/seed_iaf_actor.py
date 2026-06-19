#!/usr/bin/env python3
"""联调：为已知 IAF sub 写入 actor_projection + actor_org_role_binding（不依赖 IAF 配角色 API）。

用法（连到目标 PG，由 ZW_BRAIN_DATABASE_URL 指定）::

  export ZW_BRAIN_DATABASE_URL='postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain'
  python3 scripts/dev/seed_iaf_actor.py \\
    --iaf-sub '<你的IAF sub>' \\
    --username zhangsan \\
    --display-name '联调-张三' \\
    --org-code ORG-DEBUG-001 \\
    --roles ROLE_ORGAN_OPERATER,ROLE_ORGAN_MANAGER

或在容器内（需把本脚本拷入容器或挂载仓库）::

  docker exec -e ZW_BRAIN_DATABASE_URL='postgresql+psycopg://...' zw-brain-rest \\
    python3 /path/to/seed_iaf_actor.py --iaf-sub '...' ...

写入后：用户重新走 IAF 登录；需已部署「IAM 无 ROLE_* 时保留本地 binding」修复。

⚠️ 数据风险：本脚本调用 ensure_runtime_schema()。若目标 DB 的 actor_org_role_binding
表缺少 PR #74 新增列（tags_json / batch_no / source_priority / valid_from / valid_to /
granted_by），存量库会被识别为真漂移；带 --allow-schema-reset 时才走 reset_and_upgrade()
（drop & recreate，**整库内所有已写入数据将丢失**）。请先确认 DB 已升至 PR #74 schema 或
目标 DB 内无需保留的数据。脚本在主流程前会探测一次，若发现要 reset 则要求显式 --allow-schema-reset。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# 角色码权威源：从 zw_brain.domain.role_codes 派生，避免多处硬编码漂移。
# 业务角色（6 个）允许 seed；系统角色（admin / system）不通过 seed 工具写入。
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES  # noqa: E402

VALID_ROLE_CODES: frozenset[str] = frozenset(BUSINESS_ROLE_CODES)


def _parse_roles(raw: str) -> list[str]:
    roles = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [r for r in roles if r not in VALID_ROLE_CODES]
    if unknown:
        raise SystemExit(f"无效 role_code: {unknown}；允许: {sorted(VALID_ROLE_CODES)}")
    if not roles:
        raise SystemExit("至少指定一个 --roles")
    return roles


def main() -> int:
    parser = argparse.ArgumentParser(description="联调：为 IAF sub 种子治理投影与 org-role binding")
    parser.add_argument("--iaf-sub", required=True, help="IAF token 中的 sub（= external_actor_id）")
    parser.add_argument("--tenant-id", default="sd-default", help="租户，默认 sd-default")
    parser.add_argument("--org-code", default="ORG-DEBUG-001", help="默认组织码")
    parser.add_argument("--org-name", default="", help="组织显示名，默认同 org-code")
    parser.add_argument(
        "--roles",
        default="ROLE_ORGAN_OPERATER",
        help="逗号分隔产品角色，如 ROLE_ORGAN_OPERATER,ROLE_ORGAN_MANAGER",
    )
    parser.add_argument("--display-name", default="", help="显示名，默认 联调-<username>")
    parser.add_argument("--username", default="", help="写入 profile_json.preferred_username / account")
    parser.add_argument(
        "--default-role",
        default="",
        help="会话默认角色（须在 --roles 内）；默认取 --roles 第一个",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="覆盖 ZW_BRAIN_DATABASE_URL，如 postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将写入的数据，不写库")
    parser.add_argument(
        "--allow-schema-reset",
        action="store_true",
        help="若目标 DB 的 actor_org_role_binding 缺少 PR #74 新增列，允许 drop & recreate（清空整库）。",
    )
    args = parser.parse_args()

    if args.database_url:
        os.environ["ZW_BRAIN_DATABASE_URL"] = str(args.database_url).strip()

    database_url = os.environ.get("ZW_BRAIN_DATABASE_URL", "")
    if not database_url:
        print("请设置 ZW_BRAIN_DATABASE_URL 或 --database-url", file=sys.stderr)
        return 1

    iaf_sub = str(args.iaf_sub).strip()
    if not iaf_sub:
        print("--iaf-sub 不能为空", file=sys.stderr)
        return 1

    tenant_id = str(args.tenant_id).strip()
    org_code = str(args.org_code).strip()
    org_name = str(args.org_name or org_code).strip()
    username = str(args.username or iaf_sub).strip()
    display_name = str(args.display_name or f"联调-{username}").strip()
    role_codes = _parse_roles(args.roles)
    default_role = str(args.default_role or role_codes[0]).strip()
    if default_role not in role_codes:
        raise SystemExit(f"--default-role {default_role!r} 不在 --roles 列表中")

    bindings = [
        {"org_code": org_code, "role_code": role, "tags_json": {}, "source_priority": "debug:seed"}
        for role in role_codes
    ]
    actor_payload = {
        "iaf_sub": iaf_sub,
        "display_name": display_name,
        "org_code": org_code,
        "role_codes": role_codes,
        "status": "active",
        "source_ref": "debug:seed_iaf_actor",
        "profile_json": {
            "iaf_sub": iaf_sub,
            "account": username,
            "preferred_username": username,
            "binding_status": "bound",
            "seed_tool": "scripts/dev/seed_iaf_actor.py",
        },
    }

    plan = {
        "database_url": database_url,
        "tenant_id": tenant_id,
        "org": {"org_code": org_code, "org_name": org_name},
        "actor": actor_payload,
        "bindings": bindings,
        "session_default_role": default_role,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    # Schema drift 探测：若 actor_org_role_binding 缺 PR #74 新列，ensure_runtime_schema()
    # 会触发 drop & recreate 清空整库。要求显式 --allow-schema-reset。
    from sqlalchemy import create_engine, inspect

    from zw_brain.shared.db import get_database_url
    from zw_brain.shared.migrate import REQUIRED_COLUMNS

    engine = create_engine(get_database_url(), future=True)
    try:
        inspector = inspect(engine)
        if "actor_org_role_binding" in inspector.get_table_names():
            existing_columns = {c["name"] for c in inspector.get_columns("actor_org_role_binding")}
            missing = REQUIRED_COLUMNS["actor_org_role_binding"] - existing_columns
            if missing and not args.allow_schema_reset:
                print(
                    f"⚠️ 目标 DB 缺少 PR #74 新增列 {sorted(missing)}；继续将触发整库 drop & recreate。\n"
                    "如需丢弃整库数据并升级 schema，请再加 --allow-schema-reset 重试；否则先备份 DB 或换一个空 DB。",
                    file=sys.stderr,
                )
                return 2
    finally:
        engine.dispose()

    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    repo = GovernanceProjectionRepository()
    repo.upsert_org(
        {"org_code": org_code, "org_name": org_name, "status": "active", "source_ref": "debug:seed"},
        tenant_id=tenant_id,
    )
    for role in role_codes:
        repo.upsert_role(
            {
                "role_code": role,
                "role_name": role,
                "status": "active",
                "source_ref": "debug:seed",
            },
            tenant_id=tenant_id,
        )
    actor = repo.upsert_actor(actor_payload, tenant_id=tenant_id)
    repo.sync_actor_bindings(actor, bindings, batch_no="debug-seed-iaf-actor")

    contexts = repo.list_active_actor_contexts(tenant_id=tenant_id, external_actor_id=iaf_sub)
    print("\n=== 写入完成 ===")
    print(f"external_actor_id: {actor.external_actor_id}")
    print(f"role_codes_json:   {actor.role_codes_json}")
    print(f"active bindings:   {len(contexts)}")
    for ctx in contexts:
        print(f"  - org={ctx['org_code']} role={ctx['role_code']} tags={ctx.get('actor_tags')}")
    print("\n下一步: 浏览器退出后重新 IAF 登录；或 curl POST /auth/iaf/token 换票验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
