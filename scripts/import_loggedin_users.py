#!/usr/bin/env python3
"""
将 .data/export_loggedin_users_with_full_roles.json 中的 8 个用户导入 PostgreSQL。

用法:
  python scripts/import_loggedin_users.py
  python scripts/import_loggedin_users.py --json-path .data/export_loggedin_users_with_full_roles.json
  python scripts/import_loggedin_users.py --db-url "postgresql+psycopg://..."

表:
  - org_projection        (ORG-DEBUG-001)
  - actor_projection      (8 个用户)
  - actor_org_role_binding (每个用户多个角色绑定)
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path


def load_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def connect(db_url: str):
    import psycopg
    return psycopg.connect(db_url.replace("+psycopg", ""))


def ensure_org(conn, tenant_id: str, org_info: dict) -> list[str]:
    """确保 org_projection 中存在目标组织。返回 warnings。"""
    warnings: list[str] = []
    org_code = org_info["org_code"]
    oc = conn.cursor()
    oc.execute(
        "SELECT 1 FROM org_projection WHERE tenant_id = %s AND org_code = %s",
        (tenant_id, org_code),
    )
    if oc.fetchone():
        print(f"  组织 {org_code} 已存在，跳过")
    else:
        now = datetime.now(UTC).isoformat()
        oc.execute(
            """INSERT INTO org_projection (id, tenant_id, org_code, org_name, parent_org_code,
               region_code, status, source_ref, profile_json, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                str(uuid.uuid4()),
                tenant_id,
                org_code,
                org_info.get("org_name", org_code),
                None,
                None,
                org_info.get("status", "active"),
                "iam:provision",
                "{}",
                now,
            ),
        )
        print(f"  创建组织 {org_code}")
    oc.close()
    return warnings


def upsert_actor(conn, tenant_id: str, user: dict) -> str | None:
    """写入 actor_projection，返回 iaf_sub 或 error。"""
    iaf_sub = user["iaf_sub"]
    username = user["username"]
    display_name = user.get("display_name", username)
    org_code = user.get("org_code")
    role_codes = user.get("role_codes", [])
    evidence = user.get("match_evidence", {"method": "iaf_sub", "result": "new"})
    email = user.get("email", "")

    profile = {
        "iaf_sub": iaf_sub,
        "username": username,
        "email": email,
        "source": "export_loggedin_users",
        "match_evidence": evidence,
    }

    now = datetime.now(UTC).isoformat()
    oc = conn.cursor()

    # 检查是否已存在
    oc.execute(
        "SELECT id, profile_json FROM actor_projection WHERE tenant_id = %s AND external_actor_id = %s",
        (tenant_id, iaf_sub),
    )
    existing = oc.fetchone()

    if existing:
        existing_id, existing_profile = existing
        # 更新 profile 中的 iaf_sub
        if isinstance(existing_profile, dict):
            existing_profile.update(profile)
        else:
            existing_profile = profile

        oc.execute(
            """UPDATE actor_projection SET
               display_name = %s, org_code = %s, role_codes_json = %s,
               status = %s, source_ref = %s, profile_json = %s, updated_at = %s
               WHERE id = %s""",
            (
                display_name,
                org_code,
                json.dumps(role_codes, ensure_ascii=False),
                "active",
                "iam:provision",
                json.dumps(existing_profile, ensure_ascii=False),
                now,
                existing_id,
            ),
        )
        print(f"    actor_projection: {username}({iaf_sub[:8]}...) 已存在，更新")
        oc.close()
        return iaf_sub

    oc.execute(
        """INSERT INTO actor_projection
           (id, tenant_id, external_actor_id, display_name, org_code,
            role_codes_json, status, source_ref, profile_json, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            str(uuid.uuid4()),
            tenant_id,
            iaf_sub,
            display_name,
            org_code,
            json.dumps(role_codes, ensure_ascii=False),
            "active",
            "iam:provision",
            json.dumps(profile, ensure_ascii=False),
            now,
        ),
    )
    print(f"    actor_projection: {username}({iaf_sub[:8]}...) 已创建")
    oc.close()
    return iaf_sub


def upsert_bindings(conn, tenant_id: str, iaf_sub: str, bindings: list[dict]) -> int:
    """写入 actor_org_role_binding，返回写入条数。"""
    count = 0
    now = datetime.now(UTC).isoformat()
    oc = conn.cursor()

    for b in bindings:
        org_code = b["org_code"]
        role_code = b["role_code"]
        bstatus = b.get("binding_status", "active")
        source_ref = b.get("source_ref", "iam:provision")

        # 检查是否已有这条绑定
        oc.execute(
            """SELECT 1 FROM actor_org_role_binding
               WHERE tenant_id = %s AND external_actor_id = %s
               AND org_code = %s AND role_code = %s""",
            (tenant_id, iaf_sub, org_code, role_code),
        )
        if oc.fetchone():
            # 已存在，更新
            oc.execute(
                """UPDATE actor_org_role_binding SET
                   binding_status = %s, source_ref = %s, updated_at = %s
                   WHERE tenant_id = %s AND external_actor_id = %s
                   AND org_code = %s AND role_code = %s""",
                (bstatus, source_ref, now, tenant_id, iaf_sub, org_code, role_code),
            )
        else:
            oc.execute(
                """INSERT INTO actor_org_role_binding
                   (id, tenant_id, external_actor_id, org_code, role_code,
                    binding_status, tags_json, evidence_json, source_ref, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    iaf_sub,
                    org_code,
                    role_code,
                    bstatus,
                    json.dumps({}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    source_ref,
                    now,
                ),
            )
        count += 1

    oc.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="导入导出用户数据到 PostgreSQL")
    parser.add_argument("--json-path", default=".data/export_loggedin_users_with_full_roles.json")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--tenant", default="sd-default")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"错误: 文件不存在: {json_path}")
        return 1

    db_url = args.db_url or os.environ.get(
        "ZW_BRAIN_DATABASE_URL",
        "postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain",
    )

    data = load_json(json_path)
    tenant_id = data.get("tenant_id", args.tenant)
    org_info = data.get("org", {})
    users = data.get("users", [])

    print(f"租户: {tenant_id}")
    print(f"组织: {org_info.get('org_code', 'N/A')}")
    print(f"用户数: {len(users)}")
    print()

    if args.dry_run:
        print("[dry-run] 以下操作将被执行:")
        print(f"  1. 创建组织 {org_info.get('org_code')}")
        for u in users:
            print(f"  2. 写入 actor_projection: {u['username']} ({u['iaf_sub'][:8]}...)")
            print(f"     -> {len(u.get('actor_org_role_bindings', []))} 条角色绑定")
        print()
        print("[dry-run] 未写入数据库")
        return 0

    conn = connect(db_url)
    try:
        # Step 1: 确保组织存在
        print("Step 1: 检查/创建组织 ...")
        ensure_org(conn, tenant_id, org_info)
        conn.commit()

        # Step 2: 写入用户
        print("\nStep 2: 写入用户 ...")
        success = 0
        for u in users:
            iaf_sub = upsert_actor(conn, tenant_id, u)
            if iaf_sub:
                success += 1
        conn.commit()
        print(f"  actor_projection: {success}/{len(users)} 成功")

        # Step 3: 写入角色绑定
        print("\nStep 3: 写入角色绑定 ...")
        total_bindings = 0
        for u in users:
            iaf_sub = u["iaf_sub"]
            bindings = u.get("actor_org_role_bindings", [])
            n = upsert_bindings(conn, tenant_id, iaf_sub, bindings)
            total_bindings += n
        conn.commit()
        print(f"  actor_org_role_binding: {total_bindings} 条")

        print(f"\n{'='*50}")
        print("完成!")
        print(f"  组织: {org_info.get('org_code')}")
        print(f"  用户: {success}")
        print(f"  绑定: {total_bindings}")

    except Exception as e:
        conn.rollback()
        print(f"\n错误: {e}")
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
