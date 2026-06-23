#!/usr/bin/env python3
"""
根据 BSP dump 中用户角色关系，通过 role-mapping-manifest 映射更新数据库中用户角色信息。

策略：
- 只更新 actor_projection.role_codes_json 和 actor_org_role_binding 表
- 不修改 display_name / status / org_code / source_ref / profile_json 等字段
- 对已手动分配角色的 IAM 用户（已有 role_codes_json），跳过，不覆盖
- 对旧系统状态为 iam_account_missing 的用户，只清理旧角色，不写入新角色
- 对 IAM 用户（iam:provision / iaf:claims），按 account 匹配 dump 中角色，写入

    用法：
    uv run python scripts/update_user_roles.py [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES, LEGACY_ROLE_CODES

# ── 路径 ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
DUMP_PATH = REPO_ROOT / ".data.bak/old/10示例数据/dump-dsp_bsp-202604271139.sql"
MANIFEST_PATH = REPO_ROOT / "tests/fixtures/m0-sd-default/role-mapping-manifest.json"

os.environ.setdefault("ZW_BRAIN_DATABASE_URL",
    "postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain")
DB_URL = os.environ["ZW_BRAIN_DATABASE_URL"]

# ── 产品角色白名单 ─────────────────────────────────────────────────────────
PRODUCT_ROLES = frozenset(BUSINESS_ROLE_CODES)


def parse_dump(filepath: Path) -> dict[str, list[dict[str, str]]]:
    from zw_brain.adapters.legacy.parser import MysqldumpParser
    tables: dict[str, list[dict[str, str]]] = {}
    for table, row in MysqldumpParser(filepath).iter_rows():
        tables.setdefault(table, []).append(row)
    return tables


def load_manifest(filepath: Path) -> dict[str, dict[str, str | None]]:
    blob = json.loads(filepath.read_text(encoding="utf-8"))
    mapping: dict[str, dict[str, str | None]] = {}
    for row in blob.get("rows", []):
        ref = str(row.get("legacy_role_ref") or "").strip()
        if not ref:
            continue
        mapping[ref] = {
            "target_type": str(row.get("target_type") or "role"),
            "target_role_code": str(row.get("target_role_code") or ""),
            "target_tag": row.get("target_tag") or None,
        }
    return mapping


def normalize_role(legacy_role: str, mapping: dict) -> dict | None:
    role = legacy_role.strip()
    if not role or role.lower() in LEGACY_ROLE_CODES:
        return None
    m = mapping.get(role)
    if m is None:
        return None
    target_type = m["target_type"]
    target_role_code = m["target_role_code"]
    if target_type == "tag":
        if target_role_code in PRODUCT_ROLES:
            tag = m.get("target_tag")
            return {"role_code": target_role_code, "tags_json": {tag: True} if tag else {}}
        return None
    if target_role_code not in PRODUCT_ROLES:
        return None
    return {"role_code": target_role_code, "tags_json": {}}


def collect_dump_user_roles(
    tables: dict[str, list[dict[str, str]]],
    mapping: dict,
    verbose: bool = False,
) -> dict[str, dict]:
    """从 dump 中提取每个旧用户 ID 的角色信息。

    返回: {user_id: {"role_codes": list[str], "bindings": [...], "account": str, "org_code": str}}
    """
    users_by_id: dict[str, dict] = {}
    for row in tables.get("pub_user", []):
        uid = str(row.get("ID", "")).strip()
        if uid:
            users_by_id[uid] = row

    # pub_user_organ_role: (user_code) -> [(org_code, role)]
    organ_roles: list[tuple[str, str, str]] = []
    for row in tables.get("pub_user_organ_role", []):
        ucode = str(row.get("USER_CODE", "")).strip()
        org_code = str(row.get("ORG_CODE", "")).strip()
        raw_role = str(row.get("ROLE_CODE", "")).strip()
        if ucode and org_code and raw_role:
            organ_roles.append((ucode, org_code, raw_role))

    # pub_user_role: user_id -> [raw_role_code]
    user_role_map: dict[str, list[str]] = defaultdict(list)
    for row in tables.get("pub_user_role", []):
        ucode = str(row.get("USER_CODE", "")).strip()
        raw_role = str(row.get("ROLE_CODE", "")).strip()
        if ucode and raw_role:
            user_role_map[ucode].append(raw_role)

    result: dict[str, dict] = {}

    for uid, row in users_by_id.items():
        account = str(row.get("ACCOUNT", "")).strip()
        ucode = str(row.get("USER_CODE", "")).strip() or uid
        main_org = str(row.get("ORG_CODE", "")).strip()

        role_set: set[str] = set()
        bindings: list[dict] = []
        binding_keys: set[tuple[str, str]] = set()

        # 优先级1: pub_user_organ_role（组织+角色）
        for ucode2, org_code, raw_role in organ_roles:
            if ucode2 != ucode:
                continue
            for role_part in raw_role.split("#"):
                role_part = role_part.strip()
                if not role_part:
                    continue
                n = normalize_role(role_part, mapping)
                if n is None:
                    continue
                role_set.add(n["role_code"])
                key = (org_code, n["role_code"])
                if key not in binding_keys:
                    binding_keys.add(key)
                    bindings.append({
                        "org_code": org_code,
                        "role_code": n["role_code"],
                        "tags_json": n["tags_json"],
                    })

        # 优先级2: pub_user_role（主组织下+角色）
        if main_org:
            for raw_role in user_role_map.get(uid, []):
                for role_part in raw_role.split("#"):
                    role_part = role_part.strip()
                    if not role_part:
                        continue
                    n = normalize_role(role_part, mapping)
                    if n is None:
                        continue
                    role_set.add(n["role_code"])
                    key = (main_org, n["role_code"])
                    if key not in binding_keys:
                        binding_keys.add(key)
                        bindings.append({
                            "org_code": main_org,
                            "role_code": n["role_code"],
                            "tags_json": n["tags_json"],
                        })

        # 优先级3: pub_user.ROLE_VALUE/ROLE_CODE 兜底
        if main_org and not bindings:
            raw_value = str(row.get("ROLE_VALUE") or row.get("ROLE_CODE") or "").strip()
            if raw_value:
                for role_part in raw_value.split(","):
                    role_part = role_part.strip()
                    if not role_part:
                        continue
                    n = normalize_role(role_part, mapping)
                    if n is None:
                        continue
                    role_set.add(n["role_code"])
                    key = (main_org, n["role_code"])
                    if key not in binding_keys:
                        binding_keys.add(key)
                        bindings.append({
                            "org_code": main_org,
                            "role_code": n["role_code"],
                            "tags_json": n["tags_json"],
                        })

        result[uid] = {
            "role_codes": sorted(role_set),
            "bindings": bindings,
            "account": account,
            "org_code": main_org,
        }

        if verbose and role_set:
            print(f"  [dump] user={account}({uid[:12]}...) "
                  f"roles={sorted(role_set)} bindings={len(bindings)}")

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, default=DUMP_PATH,
                        help=f"BSP SQL dump 路径 (默认: {DUMP_PATH.relative_to(REPO_ROOT)})")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH,
                        help=f"role-mapping-manifest.json 路径 (默认: {MANIFEST_PATH.relative_to(REPO_ROOT)})")
    parser.add_argument("--tenant", default="sd-default",
                        help="目标租户 ID (默认: sd-default)")
    parser.add_argument("--db-url", default=DB_URL,
                        help="PostgreSQL 连接 URL (默认: ZW_BRAIN_DATABASE_URL 或本地默认)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只预览，不执行更新")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="输出详细信息")
    args = parser.parse_args()
    is_dry = args.dry_run
    tenant_id = args.tenant

    print("=" * 60)
    print("1. 加载 role-mapping-manifest...")
    manifest = load_manifest(args.manifest)
    print(f"   manifest 行数: {len(manifest)}")

    print("=" * 60)
    print("2. 解析 BSP dump...")
    tables = parse_dump(args.dump)
    print(f"   pub_user: {len(tables.get('pub_user', []))} 行 "
          f"pub_role: {len(tables.get('pub_role', []))} 行 "
          f"pub_user_role: {len(tables.get('pub_user_role', []))} 行 "
          f"pub_user_organ_role: {len(tables.get('pub_user_organ_role', []))} 行")

    print("=" * 60)
    print("3. 计算 dump 用户角色...")
    dump_roles = collect_dump_user_roles(tables, manifest, verbose=args.verbose)
    users_with_roles = {uid for uid, info in dump_roles.items() if info["role_codes"]}
    print(f"   dump 用户: {len(dump_roles)}, 有角色: {len(users_with_roles)}")

    from sqlalchemy import create_engine, text
    engine = create_engine(args.db_url)

    with engine.connect() as conn:
        # 读取所有 actor_projection
        rows = conn.execute(text("""
            SELECT external_actor_id, display_name, status, source_ref,
                   role_codes_json::text as role_codes_text,
                   profile_json::text as profile_text
            FROM actor_projection
            WHERE tenant_id = :tenant_id
            ORDER BY external_actor_id
        """), {"tenant_id": tenant_id}).fetchall()

        actors: list[dict] = []
        actor_by_legacy_ref: dict[str, dict] = {}
        actor_by_name: dict[str, list[dict]] = defaultdict(list)
        known_actors_with_role: set[str] = set()  # 已有角色的 IAM 用户，跳过

        for r in rows:
            info = {
                "external_actor_id": r[0],
                "display_name": r[1],
                "status": r[2],
                "source_ref": r[3],
                "role_codes_json": json.loads(r[4]) if r[4] else [],
                "profile_json": json.loads(r[5]) if r[5] else {},
            }
            actors.append(info)
            legacy_ref = info["profile_json"].get("legacy_actor_ref")
            if legacy_ref:
                actor_by_legacy_ref[legacy_ref] = info
            name = info["display_name"].lower()
            if name:
                actor_by_name[name].append(info)
            # 已有角色且来源不是 dsp-bsp 的，标记为"已知有角色用户"跳过
            if info["role_codes_json"] and info["source_ref"] != "iaf:claims":
                if info["source_ref"] == "iam:provision" or info["source_ref"] == "iaf:claims":
                    known_actors_with_role.add(info["external_actor_id"])

        # 额外保留：当前有 binding 的用户
        binding_users = set(row[0] for row in conn.execute(text("""
            SELECT DISTINCT external_actor_id FROM actor_org_role_binding
            WHERE tenant_id = :tenant_id
        """), {"tenant_id": tenant_id}).fetchall())
        known_actors_with_role.update(binding_users)

        print(f"\n   数据库中 actor_projection: {len(rows)} 行")
        print(f"   旧系统用户(由legacy_ref索引): {len(actor_by_legacy_ref)}")
        print(f"   已有角色的IAM用户(跳过): {len(known_actors_with_role)}")

        if args.verbose and known_actors_with_role:
            for eid in sorted(known_actors_with_role):
                info = next((a for a in actors if a["external_actor_id"] == eid), None)
                if info:
                    print(f"   [skip-keep] {info['display_name']:25s} "
                          f"roles={info['role_codes_json']}")

        print("\n" + "=" * 60)
        print("4. 处理旧系统用户 (dsp-bsp) — 清理旧角色")
        print("=" * 60)

        legacy_clear_count = 0
        legacy_role_users_found = 0

        for legacy_ref, actor_info in sorted(actor_by_legacy_ref.items()):
            if legacy_ref not in dump_roles:
                continue
            dump_info = dump_roles[legacy_ref]
            if not dump_info["role_codes"]:
                continue
            legacy_role_users_found += 1

            if actor_info["status"] == "iam_account_missing":
                eid = actor_info["external_actor_id"]
                if actor_info["role_codes_json"] or eid in binding_users:
                    if args.verbose or True:
                        print(f"   [clear] {actor_info['display_name']:20s} "
                              f"旧角色: {actor_info['role_codes_json'] or '有binding'}"
                              f" → 清空 (IAM未绑定)")
                    if is_dry:
                        legacy_clear_count += 1
                    else:
                        conn.execute(text("""
                            UPDATE actor_projection
                            SET role_codes_json = CAST(:empty_json AS jsonb)
                            WHERE tenant_id = :tenant_id
                              AND external_actor_id = :eid
                              AND role_codes_json::text != '[]'
                        """), {"tenant_id": tenant_id, "eid": eid, "empty_json": "[]"})
                        dr = conn.execute(text("""
                            DELETE FROM actor_org_role_binding
                            WHERE tenant_id = :tenant_id
                              AND external_actor_id = :eid
                        """), {"tenant_id": tenant_id, "eid": eid})
                        if dr.rowcount > 0 or args.verbose:
                            pass  # 计数只会计一次
                        legacy_clear_count += 1
                    conn.commit()

        print(f"   旧系统用户有角色的: {legacy_role_users_found} (IAM未绑定)")
        print(f"   已清理旧角色的: {legacy_clear_count}")

        # 额外清理：旧系统用户但有 binding 但 status 不是 active 的
        for _legacy_ref, actor_info in sorted(actor_by_legacy_ref.items()):
            if actor_info["status"] == "iam_account_missing":
                eid = actor_info["external_actor_id"]
                if eid in binding_users:
                    if not is_dry:
                        conn.execute(text("""
                            DELETE FROM actor_org_role_binding
                            WHERE tenant_id = :tenant_id
                              AND external_actor_id = :eid
                        """), {"tenant_id": tenant_id, "eid": eid})
                        conn.execute(text("""
                            UPDATE actor_projection
                            SET role_codes_json = CAST(:empty_json AS jsonb)
                            WHERE tenant_id = :tenant_id
                              AND external_actor_id = :eid
                        """), {"tenant_id": tenant_id, "eid": eid, "empty_json": "[]"})
                        conn.commit()

        print("\n" + "=" * 60)
        print("5. 处理 IAM 用户 — 按 account 匹配写入角色")
        print("=" * 60)

        # 建立 dump 中 account -> roles 的索引
        dump_by_account: dict[str, dict] = {}
        for _uid, info in dump_roles.items():
            acct = info["account"]
            if acct:
                dump_by_account[acct] = info

        iam_update_count = 0
        iam_binding_insert = 0
        iam_skip_known = 0
        iam_no_match = 0
        for actor_info in actors:
            if actor_info["source_ref"] not in ("iam:provision", "iaf:claims"):
                continue

            eid = actor_info["external_actor_id"]
            name = actor_info["display_name"].lower()

            # 跳过已有角色的 IAM 用户（开发/测试账号）
            if eid in known_actors_with_role:
                iam_skip_known += 1
                if args.verbose:
                    print(f"   [skip-keep] {actor_info['display_name']:25s} "
                          f"已有角色: {actor_info['role_codes_json']}")
                continue

            # 在 dump 中按 account 查找
            dump_info = dump_by_account.get(name)
            if dump_info is None:
                iam_no_match += 1
                if args.verbose:
                    print(f"   [no-match] {actor_info['display_name']:25s} dump中无此account")
                continue

            role_codes = dump_info["role_codes"]
            bindings = dump_info["bindings"]

            # 确认组织 code 在 binding 中填充的是正确的
            # IAM 用户的 org_code 可能需要从 actor_projection 获取，如果 binding 中有组织的话
            _actor_org = actor_info.get("profile_json", {}).get("org_code") or actor_info.get("org_code") or ""

            if is_dry:
                if role_codes:
                    print(f"   [update] {actor_info['display_name']:25s} "
                          f"roles={role_codes} bindings={len(bindings)}条")
                else:
                    print(f"   [clear]  {actor_info['display_name']:25s} dump中无角色")
                iam_update_count += 1
                iam_binding_insert += len(bindings)
            else:
                # 更新 role_codes_json
                roles_json_str = json.dumps(role_codes, ensure_ascii=False)
                conn.execute(text("""
                    UPDATE actor_projection
                    SET role_codes_json = CAST(:roles AS jsonb)
                    WHERE tenant_id = :tenant_id
                      AND external_actor_id = :eid
                """), {
                    "tenant_id": tenant_id,
                    "eid": eid,
                    "roles": roles_json_str,
                })
                iam_update_count += 1

                # 删除旧的 binding
                conn.execute(text("""
                    DELETE FROM actor_org_role_binding
                    WHERE tenant_id = :tenant_id
                      AND external_actor_id = :eid
                """), {"tenant_id": tenant_id, "eid": eid})

                # 写入新的 binding
                for b in bindings:
                    tags_str = json.dumps(b.get("tags_json", {}))
                    conn.execute(text("""
                        INSERT INTO actor_org_role_binding
                            (id, tenant_id, external_actor_id, org_code, role_code,
                             binding_status, tags_json, evidence_json, source_priority,
                             updated_at)
                        VALUES
                            (gen_random_uuid()::text, :tenant_id, :eid, :org, :role,
                             'active', CAST(:tags AS jsonb),
                             '{}'::jsonb, 'bsp_import_script',
                             NOW())
                        ON CONFLICT (tenant_id, external_actor_id, org_code, role_code)
                        DO UPDATE SET
                            binding_status = 'active',
                            tags_json = CAST(:tags AS jsonb),
                            source_priority = 'bsp_import_script',
                            updated_at = NOW()
                    """), {
                        "tenant_id": tenant_id,
                        "eid": eid,
                        "org": b["org_code"],
                        "role": b["role_code"],
                        "tags": tags_str,
                    })
                    iam_binding_insert += 1

                if args.verbose and role_codes:
                    print(f"   [update] {actor_info['display_name']:25s} "
                          f"roles={role_codes} bindings={len(bindings)}条")

                conn.commit()

        print(f"\n   IAM 用户总计: {len([a for a in actors if a['source_ref'] in ('iam:provision','iaf:claims')])}")
        print(f"   跳过(已有角色): {iam_skip_known}")
        print(f"   未匹配dump account: {iam_no_match}")
        print(f"   已更新角色: {iam_update_count}")
        print(f"   已写入binding: {iam_binding_insert}")

        print("\n" + "=" * 60)
        print("6. 最终状态")
        print("=" * 60)
        check = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM actor_projection
                 WHERE tenant_id = :tenant_id
                   AND role_codes_json::text != '[]') AS has_role,
                (SELECT COUNT(*) FROM actor_projection
                 WHERE tenant_id = :tenant_id
                   AND (role_codes_json IS NULL OR role_codes_json::text = '[]')) AS no_role,
                (SELECT COUNT(DISTINCT external_actor_id) FROM actor_org_role_binding
                 WHERE tenant_id = :tenant_id) AS users_with_binding,
                (SELECT COUNT(*) FROM actor_org_role_binding
                 WHERE tenant_id = :tenant_id) AS total_bindings
        """), {"tenant_id": tenant_id}).fetchone()
        print(f"   actor_projection 有角色: {check[0]}")
        print(f"   actor_projection 无角色: {check[1]}")
        print(f"   actor_org_role_binding 有用户: {check[2]}")
        print(f"   actor_org_role_binding 总条数: {check[3]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
