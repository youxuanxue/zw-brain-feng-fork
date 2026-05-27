#!/usr/bin/env python3
"""把 IAM 团队回填的 `legacy_user_id → iaf_sub` 表幂等灌回 iaf-binding-manifest.json。

A 线传送带的回流侧。M0 现场流程见 export_iam_provisioning_request.py 的 docstring。

输入 csv
========
IAM 团队回填的 csv 至少包含两列：

    legacy_user_id,iaf_sub[,binding_status]

- `iaf_sub` 留空（或写 `iam_account_missing` / `missing` 等 token）= 该用户在 IAM directory
  未注入；本脚本清空 `iaf_sub` 并置 `binding_status=iam_account_missing`（后续
  `legacy.bsp.mapping.import` 的 governance mapper 对**空** `iaf_sub` 与 `iaf-sd-<sha1>`
  **占位**前缀均 fail-closed 为 `iam_account_missing`；本脚本落库前另扫占位残留，见下方退出码）。
- `binding_status` 可选；若 IAM 团队明确标 `disabled` / `unmatched` 也直接落库。
- 列名大小写不敏感，BOM/空白自动 strip。
- 额外列被忽略；csv 可带表头注释行（以 `#` 开头）。

幂等性
======
- 同一份 backfill csv 反复跑结果一致。
- 不动 manifest 中其他字段（account / preferred_username / legacy_user_code）。
- 旧的 `iaf-sd-<sha1>` 占位 sub 全部视为待替换；新真实 sub 不再以 `iaf-sd-` 开头时不警告。

输出
====
- 校验通过后才就地覆写 manifest（`--dry-run` 只打摘要不写盘）。
- 摘要：处理总数、replaced / marked_missing / unchanged / not_found_in_manifest / iam_extra_rows。
- 退出码：0=通过；1=backfill 含 manifest 中不存在的 `legacy_user_id`（`not_found_in_manifest`）；
  2=落库后仍有 `iaf-sd-` 占位 sub 残留。
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
DEFAULT_MANIFEST = REPO_ROOT / "tests/fixtures/m0-sd-default/iaf-binding-manifest.json"

# `iaf-sd-<sha1>` 是 build_m0_sd_default_fixtures.py 生成的占位 sub（基线 §1.4：iaf_sub
# 必须来自 IAF directory，占位 sub 进 canonical 会污染 actor_projection 且无法过 OIDC 验签）。
# 落库后扫一遍：任何残留占位前缀都是「跳过了 IAM 注入流程」的信号，必须 fail-closed 阻断。
_PLACEHOLDER_PREFIX = "iaf-sd-"
_MISSING_TOKENS = frozenset({"", "iam_account_missing", "missing", "none", "null"})


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_backfill_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"backfill csv not found: {path}")
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        # 跳过以 # 开头的注释行
        lines = [ln for ln in fh.readlines() if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return rows
    # 列名归一化：小写 + strip
    field_map = {(name or "").strip().lower(): name for name in reader.fieldnames}
    legacy_col = field_map.get("legacy_user_id") or field_map.get("legacy_id")
    sub_col = field_map.get("iaf_sub") or field_map.get("sub")
    status_col = field_map.get("binding_status") or field_map.get("status")
    if not legacy_col or not sub_col:
        raise ValueError(
            f"backfill csv must contain columns 'legacy_user_id' and 'iaf_sub'; got: {reader.fieldnames}"
        )
    for raw in reader:
        legacy_id = (raw.get(legacy_col) or "").strip()
        if not legacy_id:
            continue
        sub = (raw.get(sub_col) or "").strip()
        status = (raw.get(status_col) or "").strip() if status_col else ""
        rows.append({"legacy_user_id": legacy_id, "iaf_sub": sub, "binding_status": status})
    return rows


def _classify(sub: str, declared_status: str) -> tuple[str, str]:
    """返回（iaf_sub_to_write, binding_status_to_write）。

    优先级：
      1. IAM 团队显式标 disabled / unmatched → 尊重判断（sub 可空可非空）
      2. sub 空或写 missing token → fail-closed `iam_account_missing`
      3. 正常路径：sub 落库，status 默认 `bound`
    """
    sub_norm = sub.strip().lower()
    status_norm = declared_status.strip().lower()
    if status_norm in {"disabled", "unmatched"}:
        return (sub.strip(), status_norm)
    if sub_norm in _MISSING_TOKENS:
        return ("", "iam_account_missing")
    return (sub.strip(), status_norm or "bound")


def _apply(
    manifest_blob: dict[str, Any],
    backfill_rows: Iterable[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    entries: list[dict[str, Any]] = list(manifest_blob.get("entries") or [])
    by_id = {str(e.get("legacy_user_id") or ""): e for e in entries}

    stats = {
        "manifest_total": len(entries),
        "backfill_rows": 0,
        "replaced": 0,
        "marked_missing": 0,
        "unchanged": 0,
        "not_found_in_manifest": 0,
        "iam_extra_rows": [],  # legacy_user_id 列表
    }

    for row in backfill_rows:
        stats["backfill_rows"] += 1
        legacy_id = row["legacy_user_id"]
        entry = by_id.get(legacy_id)
        if entry is None:
            stats["not_found_in_manifest"] += 1
            stats["iam_extra_rows"].append(legacy_id)
            continue
        new_sub, new_status = _classify(row["iaf_sub"], row["binding_status"])
        before = (str(entry.get("iaf_sub") or ""), str(entry.get("binding_status") or ""))
        # 写回
        entry["iaf_sub"] = new_sub
        entry["binding_status"] = new_status
        after = (new_sub, new_status)
        if before == after:
            stats["unchanged"] += 1
        elif new_status == "iam_account_missing":
            stats["marked_missing"] += 1
        else:
            stats["replaced"] += 1

    # description 加注水印：标识 manifest 已经被 ingest 过
    desc = manifest_blob.get("description") or ""
    watermark = " | iam-sub backfilled"
    if watermark not in desc:
        manifest_blob["description"] = desc + watermark

    return manifest_blob, stats


def _write_manifest(path: Path, blob: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _scan_residual_placeholders(blob: dict[str, Any]) -> list[str]:
    """落库后扫 entries 看是否仍有 `iaf-sd-<sha1>` 占位 sub。

    返回残留 legacy_user_id 列表（前 20 个）。任何非空残留都意味着「IAM 注入流程未跑完
    或回填漏了用户」——必须 fail-closed 阻断，不能进 canonical。
    """
    residual: list[str] = []
    for entry in blob.get("entries") or []:
        sub = str(entry.get("iaf_sub") or "")
        if sub.startswith(_PLACEHOLDER_PREFIX):
            residual.append(str(entry.get("legacy_user_id") or ""))
    return residual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backfill_csv", type=Path,
                        help="IAM 团队回填的 csv（legacy_user_id,iaf_sub[,binding_status]）")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help=f"目标 manifest (默认: {DEFAULT_MANIFEST.relative_to(REPO_ROOT)})")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打摘要，不写盘")
    parser.add_argument("--json", action="store_true",
                        help="摘要 json 打到 stdout")
    args = parser.parse_args(argv)

    manifest_blob = _load_manifest(args.manifest)
    backfill_rows = _read_backfill_csv(args.backfill_csv)
    updated_blob, stats = _apply(manifest_blob, backfill_rows)
    residual = _scan_residual_placeholders(updated_blob)

    summary = {
        "manifest_total": stats["manifest_total"],
        "backfill_rows": stats["backfill_rows"],
        "replaced": stats["replaced"],
        "marked_missing": stats["marked_missing"],
        "unchanged": stats["unchanged"],
        "not_found_in_manifest": stats["not_found_in_manifest"],
        "iam_extra_sample": stats["iam_extra_rows"][:10],
        "placeholder_residual_count": len(residual),
        "placeholder_residual_sample": residual[:20],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"manifest_total={summary['manifest_total']} backfill_rows={summary['backfill_rows']} "
            f"replaced={summary['replaced']} marked_missing={summary['marked_missing']} "
            f"unchanged={summary['unchanged']} not_found_in_manifest={summary['not_found_in_manifest']} "
            f"placeholder_residual={summary['placeholder_residual_count']}",
            file=sys.stderr,
        )

    not_found = stats["not_found_in_manifest"]
    if not_found:
        print(
            f"[FAIL] backfill csv has {not_found} row(s) whose legacy_user_id is absent from manifest "
            f"— typo / wrong manifest version / IAM 多报了用户；修正 csv 或换 manifest 后重跑。\n"
            f"sample legacy_user_id: {stats['iam_extra_rows'][:5]}",
            file=sys.stderr,
        )
        return 1

    if residual:
        print(
            f"[FAIL] {len(residual)} entry(ies) still carry `{_PLACEHOLDER_PREFIX}<sha1>` placeholder sub "
            f"after backfill — IAM 注入流程未跑完或回填漏了用户；canonical 入库前必须 fail-closed。\n"
            f"sample legacy_user_id: {residual[:5]}\n"
            f"修法：催 IAM 团队补开通 → 重跑 step 0a/0b；或在 backfill csv 把这些 legacy_user_id "
            f"显式标 `iam_account_missing`（sub 留空即可，由 _classify 兜底）。",
            file=sys.stderr,
        )
        return 2

    if not args.dry_run:
        _write_manifest(args.manifest, updated_blob)
        print(f"wrote manifest: {args.manifest}", file=sys.stderr)
    else:
        print(f"[dry-run] manifest not written: {args.manifest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
