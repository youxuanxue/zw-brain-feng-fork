#!/usr/bin/env python3
"""把 iaf-binding-manifest.json + dsp-bsp dump 派生为「IAM 开通清单 csv」。

定位
====
A 线传送带（认证信息）的输入侧。M0 现场流程：
  1. zw-brain 工程师跑 build_m0_sd_default_fixtures.py 生成 iaf-binding-manifest（占位 iaf_sub）
  2. 跑 **本脚本** 把 manifest + dump 派生为脱敏 csv —— 给 IAM 团队批量开通账号
  3. IAM 团队按 csv 在 IAF directory 注入账号，回填真实 sub
  4. 跑 ingest_iam_sub_backfill.py 把真实 sub 替换回 manifest
  5. 跑 legacy.bsp.mapping.import 把 manifest + dump 一次性导入 canonical

边界
====
- 本脚本输出**脱敏** csv（zw-brain 仓内 baseline 工件，phone/email/name 走 zw_brain.shared.sensitive_mask）
- IAM 团队真正开通账号需要明文联系方式，由客户实施工程师**另外**从客户 HR 拿到明文花名册直接交给 IAM 团队，**不**经过 zw-brain 仓库
- 仓内 csv 的作用是「IAM 团队的开通名单匹配凭据 + 部门/区划上下文」，不是联系方式 SoT
- 同基线 §1.4 / G1：密码、token、OTP_KEY、UKEY、SENSITIVE_HMAC、IP_LIST 等运行时秘密**永不**进 csv

用法
====
    uv run python scripts/export_iam_provisioning_request.py
    uv run python scripts/export_iam_provisioning_request.py --diff /path/to/previous.csv
    uv run python scripts/export_iam_provisioning_request.py --manifest /path/to/manifest.json --dump /path/to/dump.sql
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zw_brain.shared.sensitive_mask import mask_email, mask_name, mask_phone  # noqa: E402


def _safe_mask_email(value: str) -> str:
    """旧 dump 的 EMAIL 列偶有非 email 格式（hash / 内部 ID），mask_email 见无 '@' 会原样返回 →
    本场景下作 PII 泄漏对待，统一强 mask。"""
    if not value:
        return ""
    if "@" not in value:
        return "***"
    return str(mask_email(value))


def _safe_mask_phone(value: str) -> str:
    if not value:
        return ""
    return str(mask_phone(value))


def _safe_mask_name(value: str) -> str:
    if not value:
        return ""
    return str(mask_name(value))

DEFAULT_MANIFEST = REPO_ROOT / "tests/fixtures/m0-sd-default/iaf-binding-manifest.json"
DEFAULT_DUMP = REPO_ROOT / "old/10示例数据/dump-dsp_bsp-202604271139.sql"
DEFAULT_OUT = REPO_ROOT / "tests/fixtures/m0-sd-default/iam-provisioning-request.csv"

CSV_COLUMNS: tuple[str, ...] = (
    "legacy_user_id",
    "account",
    "preferred_username",
    "display_name_mask",
    "phone_mask",
    "mobile_mask",
    "email_mask",
    "org_code",
    "org_name",
    "region_code",
    "region_name",
    "is_admin_level",
    "status",
    "type_code",
    "binding_status",
    "iaf_sub_placeholder",
    "note",
)

# diff 模式排除清单（黑名单优于白名单：新增 CSV 列默认进 diff 比较，无需记忆同步两处）。
# 排除理由：
#   - legacy_user_id：作为 join key，本身不参与差异判断
#   - *_mask 列：值会随 mask level 配置漂移，跨次比较不稳定
#   - org_name / region_name：跟随 *_code 派生，code 已比较
#   - iaf_sub_placeholder：每次 export 时 manifest 中的 sub 形态，不是业务字段
#   - note：本脚本自身生成的状态标，不属于上游差异
_EXCLUDED_FROM_DIFF: frozenset[str] = frozenset({
    "legacy_user_id",
    "display_name_mask",
    "phone_mask",
    "mobile_mask",
    "email_mask",
    "org_name",
    "region_name",
    "iaf_sub_placeholder",
    "note",
})


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"iaf-binding manifest not found: {path}")
    blob = json.loads(path.read_text(encoding="utf-8"))
    entries = blob.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"manifest missing 'entries' list: {path}")
    return entries


def _load_pub_user_by_id(dump_path: Path) -> dict[str, dict[str, Any]]:
    """读 dump 抽 pub_user 行；不存在时返回空 dict，由 caller 决定 fallback。"""
    if not dump_path.exists():
        return {}
    from zw_brain.adapters.legacy.parser import MysqldumpParser

    out: dict[str, dict[str, Any]] = {}
    for table, row in MysqldumpParser(dump_path).iter_rows():
        if table != "pub_user":
            continue
        legacy_id = str(row.get("ID") or "")
        if legacy_id:
            out[legacy_id] = row
    return out


def _format_row(
    manifest_entry: dict[str, Any],
    pub_user_row: dict[str, Any] | None,
) -> dict[str, str]:
    legacy_user_id = str(manifest_entry.get("legacy_user_id") or "")
    account = str(manifest_entry.get("account") or "")
    preferred_username = str(manifest_entry.get("preferred_username") or account)
    iaf_sub_placeholder = str(manifest_entry.get("iaf_sub") or "")
    binding_status = str(manifest_entry.get("binding_status") or "")

    if pub_user_row is None:
        return {
            "legacy_user_id": legacy_user_id,
            "account": account,
            "preferred_username": preferred_username,
            "display_name_mask": "",
            "phone_mask": "",
            "mobile_mask": "",
            "email_mask": "",
            "org_code": "",
            "org_name": "",
            "region_code": "",
            "region_name": "",
            "is_admin_level": "",
            "status": "",
            "type_code": "",
            "binding_status": binding_status,
            "iaf_sub_placeholder": iaf_sub_placeholder,
            "note": "legacy_dump_missing",
        }

    display_name = pub_user_row.get("NAME") or ""
    phone = pub_user_row.get("PHONE") or ""
    mobile = pub_user_row.get("MOBILE") or ""
    email = pub_user_row.get("EMAIL") or ""

    return {
        "legacy_user_id": legacy_user_id,
        "account": account,
        "preferred_username": preferred_username,
        "display_name_mask": _safe_mask_name(str(display_name)),
        "phone_mask": _safe_mask_phone(str(phone)),
        "mobile_mask": _safe_mask_phone(str(mobile)),
        "email_mask": _safe_mask_email(str(email)),
        "org_code": str(pub_user_row.get("ORG_CODE") or ""),
        "org_name": str(pub_user_row.get("ORG_NAME") or ""),
        "region_code": str(pub_user_row.get("REGION_CODE") or ""),
        "region_name": str(pub_user_row.get("REGION_NAME") or ""),
        "is_admin_level": str(pub_user_row.get("IS_ADMIN") or ""),
        "status": str(pub_user_row.get("STATUS") or ""),
        "type_code": str(pub_user_row.get("TYPE_CODE") or ""),
        "binding_status": binding_status,
        "iaf_sub_placeholder": iaf_sub_placeholder,
        "note": "",
    }


def _build_rows(
    manifest_entries: Iterable[dict[str, Any]],
    pub_user_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in manifest_entries:
        legacy_id = str(entry.get("legacy_user_id") or "")
        if not legacy_id:
            continue
        pub_user_row = pub_user_by_id.get(legacy_id) if pub_user_by_id else None
        rows.append(_format_row(entry, pub_user_row))
    rows.sort(key=lambda r: r["legacy_user_id"])
    return rows


def _load_previous_csv(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            legacy_id = row.get("legacy_user_id") or ""
            if legacy_id:
                out[legacy_id] = row
    return out


def _diff_rows(
    current: list[dict[str, str]],
    previous_by_id: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """返回（变更行列表，stats）。变更 = added / changed；removed 不写 diff csv（IAM 不会主动撤销）。"""
    diff: list[dict[str, str]] = []
    stats = {"added": 0, "changed": 0, "unchanged": 0, "previous_only": 0}
    seen: set[str] = set()
    for row in current:
        legacy_id = row["legacy_user_id"]
        seen.add(legacy_id)
        prev = previous_by_id.get(legacy_id)
        if prev is None:
            diff.append(row | {"note": (row.get("note") or "iam_provisioning_pending")})
            stats["added"] += 1
            continue
        # 黑名单方式：CSV_COLUMNS 全员默认参与 diff，排除掉脱敏列与派生列。
        # 新增 CSV 列若属业务字段会自动进 diff，无需同步两处。
        if any(row.get(k) != prev.get(k) for k in CSV_COLUMNS if k not in _EXCLUDED_FROM_DIFF):
            diff.append(row | {"note": "iam_provisioning_changed"})
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1
    for prev_id in previous_by_id:
        if prev_id not in seen:
            stats["previous_only"] += 1
    return diff, stats


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def _summary(
    rows: list[dict[str, str]],
    *,
    dump_present: bool,
    diff_stats: dict[str, int] | None,
) -> dict[str, Any]:
    legacy_dump_missing = sum(1 for r in rows if r.get("note") == "legacy_dump_missing")
    bound = sum(1 for r in rows if r.get("binding_status") == "bound")
    return {
        "total_rows": len(rows),
        "dump_present": dump_present,
        "legacy_dump_missing": legacy_dump_missing,
        "binding_status_bound": bound,
        "diff": diff_stats,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help=f"iaf-binding-manifest.json 路径 (默认: {DEFAULT_MANIFEST.relative_to(REPO_ROOT)})")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP,
                        help="legacy BSP dump 路径；不存在时只输出 manifest 最小列")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"输出 csv 路径 (默认: {DEFAULT_OUT.relative_to(REPO_ROOT)})")
    parser.add_argument("--diff", type=Path, default=None,
                        help="增量模式：与该 csv 对比，仅输出新增/变更行")
    parser.add_argument("--json", action="store_true",
                        help="同时把摘要 json 打到 stdout")
    args = parser.parse_args(argv)

    manifest_entries = _load_manifest(args.manifest)
    pub_user_by_id = _load_pub_user_by_id(args.dump)
    dump_present = bool(pub_user_by_id)
    if not dump_present:
        print(f"[warn] dump not present at {args.dump} — emitting minimal columns; "
              f"phone/email/org/region 留空，note=legacy_dump_missing", file=sys.stderr)

    rows = _build_rows(manifest_entries, pub_user_by_id)

    diff_stats: dict[str, int] | None = None
    if args.diff is not None:
        previous_by_id = _load_previous_csv(args.diff)
        diff_rows, diff_stats = _diff_rows(rows, previous_by_id)
        _write_csv(args.out, diff_rows)
        print(f"wrote diff csv: {args.out} ({len(diff_rows)} rows)", file=sys.stderr)
    else:
        _write_csv(args.out, rows)
        print(f"wrote full csv: {args.out} ({len(rows)} rows)", file=sys.stderr)

    summary = _summary(rows, dump_present=dump_present, diff_stats=diff_stats)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"total={summary['total_rows']} bound={summary['binding_status_bound']} "
              f"legacy_dump_missing={summary['legacy_dump_missing']}", file=sys.stderr)
        if diff_stats:
            print(f"diff: added={diff_stats['added']} changed={diff_stats['changed']} "
                  f"unchanged={diff_stats['unchanged']} previous_only={diff_stats['previous_only']}",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
