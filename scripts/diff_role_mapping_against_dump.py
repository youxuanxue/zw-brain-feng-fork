#!/usr/bin/env python3
"""扫旧 BSP dump 中所有 distinct `legacy_role_ref`，diff 现有 role-mapping-manifest，
输出 baseline 未覆盖的 ROLE_*，方便现场补 manifest 行。

定位
====
- baseline `tests/fixtures/m0-sd-default/role-mapping-manifest.json` 是 sd-default 现场
  实施工程师 baseline（63 行 ROLE_* → 7 产品角色码 + tag_lead_dept）。
- 客户现场 dump 可能含 baseline 未覆盖的新 ROLE_*。mapper 见到这类 role 会留
  `missing_role_mapping` issue 但不会自动建议归属——本工具补 review 工作流。

输入
====
- dump 路径（默认本仓 sd-default sample；现场用 --dump <客户 dump 路径>）
- manifest 路径（默认本仓 baseline；现场可指向现场维护的 manifest）

输出 csv 列
=========
    legacy_role_ref, occurrence_pub_role, occurrence_pub_user_role,
    occurrence_pub_user_organ_role, total_occurrences

`occurrence_*` 列是该 role 在对应 table 的出现次数（pub_user_organ_role 已按 `#` 拆分）；
total_occurrences 用于判断 role 的覆盖优先级（高频先补）。

用法
====
    uv run python scripts/diff_role_mapping_against_dump.py
    uv run python scripts/diff_role_mapping_against_dump.py --dump <path> --manifest <path>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DUMP = REPO_ROOT / "old/10示例数据/dump-dsp_bsp-202604271139.sql"
DEFAULT_MANIFEST = REPO_ROOT / "tests/fixtures/m0-sd-default/role-mapping-manifest.json"
DEFAULT_OUT = REPO_ROOT / "tests/fixtures/m0-sd-default/role-mapping-uncovered.csv"

CSV_COLUMNS: tuple[str, ...] = (
    "legacy_role_ref",
    "occurrence_pub_role",
    "occurrence_pub_user_role",
    "occurrence_pub_user_organ_role",
    "total_occurrences",
)


def _collect_dump_roles(dump_path: Path) -> dict[str, Counter[str]]:
    """返回 `{table_name: Counter(legacy_role_ref -> count)}`。

    pub_user_organ_role.ROLE_CODE 用 `#` 分隔多角色（见 governance.py mapper 同样拆法）。
    """
    from zw_brain.adapters.legacy.parser import MysqldumpParser

    out: dict[str, Counter[str]] = {
        "pub_role": Counter(),
        "pub_user_role": Counter(),
        "pub_user_organ_role": Counter(),
    }
    for table, row in MysqldumpParser(dump_path).iter_rows():
        if table == "pub_role":
            code = str(row.get("CODE") or "").strip()
            if code:
                out["pub_role"][code] += 1
        elif table == "pub_user_role":
            code = str(row.get("ROLE_CODE") or "").strip()
            if code:
                out["pub_user_role"][code] += 1
        elif table == "pub_user_organ_role":
            raw = str(row.get("ROLE_CODE") or "")
            for code in raw.split("#"):
                code = code.strip()
                if code:
                    out["pub_user_organ_role"][code] += 1
    return out


def _load_manifest_role_refs(manifest_path: Path) -> set[str]:
    blob = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = blob.get("rows") or []
    return {str(row.get("legacy_role_ref") or "").strip() for row in rows if row.get("legacy_role_ref")}


def diff_roles(dump_counters: dict[str, Counter[str]], manifest_refs: set[str]) -> list[dict[str, int | str]]:
    """返回未覆盖 role 的 csv row dict 列表，按 total_occurrences 降序。"""
    all_roles: set[str] = set()
    for counter in dump_counters.values():
        all_roles.update(counter.keys())
    uncovered = all_roles - manifest_refs
    rows: list[dict[str, int | str]] = []
    for role in uncovered:
        in_pub_role = dump_counters["pub_role"].get(role, 0)
        in_pub_user_role = dump_counters["pub_user_role"].get(role, 0)
        in_pub_user_organ_role = dump_counters["pub_user_organ_role"].get(role, 0)
        total = in_pub_role + in_pub_user_role + in_pub_user_organ_role
        rows.append({
            "legacy_role_ref": role,
            "occurrence_pub_role": in_pub_role,
            "occurrence_pub_user_role": in_pub_user_role,
            "occurrence_pub_user_organ_role": in_pub_user_organ_role,
            "total_occurrences": total,
        })
    rows.sort(key=lambda r: (-int(r["total_occurrences"]), str(r["legacy_role_ref"])))
    return rows


def _write_csv(path: Path, rows: list[dict[str, int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP,
                        help=f"BSP dump 路径 (默认: {DEFAULT_DUMP.relative_to(REPO_ROOT)})")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help=f"role-mapping-manifest.json 路径 (默认: {DEFAULT_MANIFEST.relative_to(REPO_ROOT)})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"输出 csv 路径 (默认: {DEFAULT_OUT.relative_to(REPO_ROOT)})")
    parser.add_argument("--json", action="store_true", help="摘要 json 到 stdout")
    args = parser.parse_args(argv)

    if not args.dump.exists():
        print(f"[FAIL] dump not found: {args.dump}", file=sys.stderr)
        return 1
    if not args.manifest.exists():
        print(f"[FAIL] manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    dump_counters = _collect_dump_roles(args.dump)
    manifest_refs = _load_manifest_role_refs(args.manifest)
    uncovered_rows = diff_roles(dump_counters, manifest_refs)
    _write_csv(args.out, uncovered_rows)

    summary = {
        "dump": str(args.dump),
        "manifest": str(args.manifest),
        "out": str(args.out),
        "manifest_covered_count": len(manifest_refs),
        "dump_distinct_role_count": sum(1 for _ in {r for c in dump_counters.values() for r in c}),
        "uncovered_count": len(uncovered_rows),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"manifest_covered={summary['manifest_covered_count']} "
            f"dump_distinct={summary['dump_distinct_role_count']} "
            f"uncovered={summary['uncovered_count']} → {args.out}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
