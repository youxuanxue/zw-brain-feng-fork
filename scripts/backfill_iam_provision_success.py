#!/usr/bin/env python3
"""
将 .data/iam-provision-success.jsonl 中的 IAM 用户 iaf_sub 回填到 PostgreSQL actor_projection。

背景
====
provision_iam_users.py 成功调用 IAM API 创建了用户（已获取 iaf_sub），但写入 actor_projection
时因 jsonb 类型转换错误失败。本脚本读取该 JSONL 文件，为每个有 iaf_sub 的记录在 PG 中补建
actor_projection 行，无角色绑定——角色绑定后续由 import_loggedin_users.py 或
update_user_roles.py 完成。

用法:
  python scripts/backfill_iam_provision_success.py
  python scripts/backfill_iam_provision_success.py --jsonl-path .data/iam-provision-success.jsonl
  python scripts/backfill_iam_provision_success.py --db-url "postgresql+psycopg://..."
  python scripts/backfill_iam_provision_success.py --dry-run      # 只预览不写入

表:
  - actor_projection (92 个 IAM 用户，无角色绑定）
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jsonl-path", default=".data/iam-provision-success.jsonl",
                        help="provision_iam_users.py 产出的成功记录 JSONL 路径 (默认: .data/iam-provision-success.jsonl)")
    parser.add_argument("--db-url", default=None,
                        help="PostgreSQL 连接 URL (默认: ZW_BRAIN_DATABASE_URL 或 127.0.0.1:5433)")
    parser.add_argument("--tenant", default="sd-default", help="租户 ID (默认: sd-default)")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--verbose", "-v", action="store_true", help="输出每条记录的处理结果")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl_path)
    if not jsonl_path.exists():
        print(f"错误: 文件不存在: {jsonl_path}")
        print(f"提示: 从 zw-brain 仓库另一侧同步: cp /data/duwei05/zw-brain/.data/iam-provision-success.jsonl {jsonl_path}")
        return 1

    db_url = args.db_url or os.environ.get(
        "ZW_BRAIN_DATABASE_URL",
        "postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5433/zw_brain",
    )
    tenant_id = args.tenant
    is_dry = args.dry_run
    verbose = args.verbose

    # ── 读取 JSONL ──────────────────────────────────────────────────────
    records: list[dict] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    total = len(records)
    valid = [r for r in records if r.get("iaf_sub") and len(str(r["iaf_sub"]).strip()) > 8]
    invalid = total - len(valid)

    print(f"JSONL 总记录: {total}")
    print(f"有效(含 iaf_sub): {len(valid)}")
    print(f"无效(缺 iaf_sub): {invalid}")
    print(f"租户: {tenant_id}")
    print()

    if is_dry:
        print(f"[dry-run] 以下 {len(valid)} 条记录将被写入 actor_projection:")
        for r in valid:
            print(f"  {r['account']:<25s}  iaf_sub={r['iaf_sub'][:8]}...  phone={r.get('phone',''):<15s}  email={r.get('email','')}")
        print(f"\n[dry-run] 共 {len(valid)} 条，未写入数据库")
        return 0

    # ── 连接 DB ──────────────────────────────────────────────────────────
    try:
        import psycopg
    except ImportError:
        print("错误: 缺少 psycopg 模块，请执行: uv sync --extra postgres 或 pip install psycopg[binary]")
        return 1

    conn = psycopg.connect(db_url.replace("+psycopg", ""))
    cur = conn.cursor()
    now_ts = datetime.now(UTC).isoformat()

    created = 0
    skipped = 0
    errors: list[dict] = []

    for r in valid:
        iaf_sub = str(r["iaf_sub"]).strip()
        account = str(r.get("account", ""))
        phone = str(r.get("phone", ""))
        email = str(r.get("email", ""))

        # 检查是否已存在（幂等）
        cur.execute(
            "SELECT 1 FROM actor_projection WHERE tenant_id = %s AND external_actor_id = %s",
            (tenant_id, iaf_sub),
        )
        if cur.fetchone():
            skipped += 1
            if verbose:
                print(f"  [skip] {account:<25s} iaf_sub={iaf_sub[:8]}... 已存在")
            continue

        profile = {
            "iaf_sub": iaf_sub,
            "username": account,
            "phone": phone,
            "email": email,
            "source": "backfill_iam_provision_success",
            "provisioned_at": now_ts,
        }

        try:
            cur.execute(
                """INSERT INTO actor_projection
                   (id, tenant_id, external_actor_id, display_name, org_code,
                    role_codes_json, status, source_ref, profile_json, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    iaf_sub,
                    account,
                    None,  # org_code — 暂空，后续由 legacy 导入 / import_loggedin_users 分配
                    json.dumps([], ensure_ascii=False),  # role_codes_json
                    "active",
                    "iam:provision",
                    json.dumps(profile, ensure_ascii=False),
                    now_ts,
                ),
            )
            conn.commit()
            created += 1
            if verbose:
                print(f"  [ok]   {account:<25s} iaf_sub={iaf_sub[:8]}... 已创建")

        except Exception as e:
            conn.rollback()
            err_msg = str(e)[:200]
            errors.append({"account": account, "iaf_sub": iaf_sub, "error": err_msg})
            if verbose:
                print(f"  [err]  {account:<25s} iaf_sub={iaf_sub[:8]}... 失败: {err_msg}")

    cur.close()
    conn.close()

    # ── 汇总 ──────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("完成!")
    print(f"  总有效记录: {len(valid)}")
    print(f"  已创建:     {created}")
    print(f"  已跳过:     {skipped}")
    print(f"  错误:       {len(errors)}")

    if errors:
        print(f"\n错误详情 (前 5 条):")
        for e in errors[:5]:
            print(f"  {e['account']:<25s} {e['error']}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
