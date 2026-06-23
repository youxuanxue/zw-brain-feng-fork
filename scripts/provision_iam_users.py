#!/usr/bin/env python3
"""
批量创建 IAM 用户并同步 iaf_sub 到 PostgreSQL actor_projection 表。

用法:
  python scripts/provision_iam_users.py \
    --csv tests/fixtures/m0-sd-default/iam-provisioning-request.csv \
    --token "eyJhbG..." \
    --iam-url "https://cnp-jn-rgzn-inlinux-test.inspur.com:9443" \
    [--db-url "postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain"] \
    [--tenant "sd-default"] \
    [--success-out .data/iam-provision-success.jsonl] \
    [--fail-out .data/iam-provision-fail.jsonl]

必选参数:
  --csv         CSV 文件路径，格式: account,phone,email,password
  --token       IAM API 的 Bearer token
  --iam-url     IAM 基础 URL (如 https://cnp-jn-rgzn-inlinux-test.inspur.com:9443)

可选参数:
  --db-url      PostgreSQL 连接 URL (默认: 同 ZW_BRAIN_DATABASE_URL 或 127.0.0.1)
  --tenant      租户 ID (默认: sd-default)
  --success-out 成功结果输出文件 (默认: .data/iam-provision-success.jsonl)
  --fail-out    失败记录输出文件 (默认: .data/iam-provision-fail.jsonl)
  --dry-run     只校验不真正调用 IAM 和数据库
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from zw_brain.shared.sanitization import safe_json

# ──────────────────────────────────────────────────────────────────────
# IAM name 校验规则: 2-22 个字符，支持小写字母、数字、"-"，不能以 "-" 开头或结尾
# ──────────────────────────────────────────────────────────────────────
IAM_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,20}[a-z0-9]$")


def validate_name(name: str) -> str | None:
    """校验 IAM 用户名，不合法返回错误描述"""
    if not (2 <= len(name) <= 22):
        return f"name长度 {len(name)} 不在 2-22 范围内"
    if not IAM_NAME_RE.match(name):
        return f"name '{name}' 包含非法字符（仅支持小写字母、数字、\"-\"，不能以 \"-\" 开头或结尾）"
    return None


def build_payload(row: dict) -> tuple[dict | None, str | None]:
    """从 CSV 行构建 IAM 请求 payload。返回 (payload, error)，error 不为空表示该行无法创建。"""
    name = row.get("account", "").strip()
    phone = row.get("phone", "").strip()
    email = row.get("email", "").strip()
    password = row.get("password", "").strip()

    if not name:
        return None, "account 为空"
    if not phone:
        return None, "phone 为空"
    if not email:
        return None, "email 为空"
    if not password:
        return None, "password 为空"

    err = validate_name(name)
    if err:
        return None, err

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "password": password,
        "checkPassword": password,
    }, None


def call_iam_create_user(iam_base: str, token: str, payload: dict, timeout: int = 30) -> tuple[dict | None, str | None]:
    """调用 IAM 创建用户接口。返回 (response_json, error)。"""
    url = f"{iam_base.rstrip('/')}/auth/v1/admin/root-users"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=timeout) as resp:
            resp_body = json.loads(resp.read().decode("utf-8"))
        return resp_body, None
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {err_body[:500]}"
    except URLError as e:
        return None, f"网络错误: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"响应不是合法 JSON: {e}"
    except Exception as e:
        return None, f"未知错误: {e}"


def upsert_actor_projection(
    db_url: str,
    tenant_id: str,
    external_actor_id: str,
    display_name: str,
    phone: str,
    email: str,
) -> str | None:
    """将 IAM 用户写入 PostgreSQL actor_projection 表。返回错误信息或 None。"""
    try:
        import psycopg
    except ImportError:
        return "缺少 psycopg 模块，请执行: uv sync --extra postgres"

    now_ts = datetime.now(UTC).isoformat()
    profile = {
        "iaf_sub": external_actor_id,
        "username": display_name,
        "phone": phone,
        "email": email,
        "provisioned_at": now_ts,
    }

    sql = """
        INSERT INTO actor_projection (
            id, tenant_id, external_actor_id, display_name, org_code,
            role_codes_json, status, source_ref, profile_json, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (tenant_id, external_actor_id)
        DO UPDATE SET
            display_name = EXCLUDED.display_name,
            profile_json = EXCLUDED.profile_json,
            updated_at = EXCLUDED.updated_at
    """
    try:
        conn = psycopg.connect(db_url.replace("+psycopg", ""))
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    external_actor_id,
                    display_name,
                    None,  # org_code — 暂无组织绑定，后续由 legacy 导入分配
                    json.dumps([], ensure_ascii=False),  # role_codes_json
                    "active",
                    "iam:provision",
                    json.dumps(profile, ensure_ascii=False),
                    now_ts,
                ),
            )
        conn.commit()
        conn.close()
        return None
    except Exception as e:
        return f"数据库写入失败: {e}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量创建 IAM 用户并同步 iaf_sub 到 PG")
    parser.add_argument("--csv", required=True, help="CSV 文件路径")
    parser.add_argument("--token", required=True, help="IAM Bearer token")
    parser.add_argument("--iam-url", required=True, help="IAM 基础 URL")
    parser.add_argument("--db-url", default=None, help="PostgreSQL 连接 URL")
    parser.add_argument("--tenant", default="sd-default", help="租户 ID")
    parser.add_argument("--success-out", default=".data/iam-provision-success.jsonl", help="成功结果输出文件")
    parser.add_argument("--fail-out", default=".data/iam-provision-fail.jsonl", help="失败记录输出文件")
    parser.add_argument("--dry-run", action="store_true", help="只校验不真正调用")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"错误: CSV 文件不存在: {csv_path}")
        return 1

    db_url = args.db_url or os.environ.get("ZW_BRAIN_DATABASE_URL", "postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain")

    # 读取 CSV
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"CSV 共 {len(rows)} 条记录")

    # 创建输出目录
    success_path = Path(args.success_out)
    fail_path = Path(args.fail_out)
    success_path.parent.mkdir(parents=True, exist_ok=True)
    fail_path.parent.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0
    precheck_fail_count = 0
    iam_fail_count = 0
    db_fail_count = 0

    success_fh = success_path.open("w", encoding="utf-8")
    fail_fh = fail_path.open("w", encoding="utf-8")

    try:
        for idx, row in enumerate(rows, start=2):  # start=2 for header row=1
            account = row.get("account", "").strip()
            print(f"[{idx-1}/{len(rows)}] {account} ... ", end="", flush=True)

            # Step 1: 校验 payload
            payload, err = build_payload(row)
            if err:
                precheck_fail_count += 1
                fail_count += 1
                fail_fh.write(json.dumps({
                    "row": idx,
                    "account": account,
                    "phone": row.get("phone", ""),
                    "email": row.get("email", ""),
                    "phase": "precheck",
                    "error": err,
                    "timestamp": datetime.now(UTC).isoformat(),
                }, ensure_ascii=False) + "\n")
                print(f"✗ 校验失败: {err}")
                continue

            # Step 2: 调用 IAM 创建用户
            if args.dry_run:
                print("✓ (dry-run, 跳过 IAM)")
                continue

            resp_json, iam_err = call_iam_create_user(args.iam_url, args.token, payload)

            if iam_err:
                iam_fail_count += 1
                fail_count += 1
                fail_fh.write(json.dumps({
                    "row": idx,
                    "account": account,
                    "phone": payload["phone"],
                    "email": payload["email"],
                    "phase": "iam_api",
                    "error": iam_err,
                    "payload": safe_json(payload),
                    "timestamp": datetime.now(UTC).isoformat(),
                }, ensure_ascii=False) + "\n")
                print(f"✗ IAM 失败: {iam_err[:80]}")
                continue

            # Step 3: 写入 PostgreSQL actor_projection
            ext_id = resp_json.get("id") or resp_json.get("accountId")
            if not ext_id:
                db_fail_count += 1
                fail_count += 1
                fail_fh.write(json.dumps({
                    "row": idx,
                    "account": account,
                    "phase": "parse_response",
                    "error": "IAM 响应中没有 id/accountId",
                    "iam_response": safe_json(resp_json),
                    "timestamp": datetime.now(UTC).isoformat(),
                }, ensure_ascii=False) + "\n")
                print("✗ 响应无 id")
                continue

            db_err = upsert_actor_projection(
                db_url=db_url,
                tenant_id=args.tenant,
                external_actor_id=ext_id,
                display_name=account,
                phone=payload["phone"],
                email=payload["email"],
            )

            # Step 4: 记录结果
            record = {
                "row": idx,
                "account": account,
                "phone": payload["phone"],
                "email": payload["email"],
                "iaf_sub": ext_id,
                "iam_response": safe_json(resp_json),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if db_err:
                db_fail_count += 1
                fail_count += 1
                record["phase"] = "db_upsert"
                record["error"] = db_err
                fail_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"✗ 数据库失败: {db_err[:80]}")
                # IAM 已创建成功但 DB 写入失败，仍记录到成功文件方便后续重试 DB 写入
                success_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                success_count += 1
                success_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"✓ iaf_sub={ext_id[:8]}...")

            # 加个小延迟避免 IAM 限流
            time.sleep(0.1)

    finally:
        success_fh.close()
        fail_fh.close()

    # 汇总
    print(f"\n{'='*60}")
    print(f"完成! 成功: {success_count}  失败: {fail_count}")
    print(f"  预检失败: {precheck_fail_count}")
    print(f"  IAM 失败: {iam_fail_count}")
    print(f"  DB 失败:   {db_fail_count}")
    print(f"成功记录: {success_path}")
    print(f"失败记录: {fail_path}")
    if args.dry_run:
        print("(dry-run 模式，未实际调用 IAM 和数据库)")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
