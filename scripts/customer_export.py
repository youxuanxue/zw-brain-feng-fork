#!/usr/bin/env python3
"""Customer-site legacy database export post-processor.

This script is the heavy-lifting half of `scripts/customer_export.sh`. It can
also run standalone in dry-run mode (`--from-dir <dir>`) against the
sanitized samples in `old/10示例数据/` so that the contract is fully testable
without an actual MySQL connection.

Subcommands
-----------
postprocess  Apply redaction rules to one raw mysqldump file and emit
             a redacted dump + per-file `.crc` and `.rowcount` artifacts.

bundle       Iterate a directory of `dump-<schema>-<ts>.sql` files, run
             postprocess on each, and emit `manifest.json` describing the
             batch (batch_id, tenant_id, file hashes, total row counts,
             redaction summary).

verify       Re-read an emitted batch directory and validate manifest.json
             against on-disk file hashes. Used by the bash entry script
             before declaring success.

Why bash + python
-----------------
mysqldump is a system tool; the orchestration belongs in bash. Streaming
parsing, redaction, and JSON manifest emission belong in Python where we
can reuse `zw_brain.adapters.legacy.parser.MysqldumpParser`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._export_redaction_rules import (  # noqa: E402
    RedactionConfig,
    load_redaction_config,
    mask_value,
)
from zw_brain.adapters.legacy.parser import MysqldumpParser  # noqa: E402

# Filename convention: dump-<schema>-<timestamp>.sql
DUMP_NAME_RE = re.compile(r"^dump-([a-z0-9_]+?)-\d+\.sql$", re.IGNORECASE)

INSERT_LINE_RE = re.compile(r"^INSERT INTO `([^`]+)` VALUES (.+);\s*$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_post = sub.add_parser("postprocess", help="Redact one dump file")
    p_post.add_argument("--input", required=True, type=Path)
    p_post.add_argument("--output", required=True, type=Path)
    p_post.add_argument("--datastructure-dir", type=Path, default=None)
    p_post.set_defaults(func=cmd_postprocess)

    p_bundle = sub.add_parser("bundle", help="Postprocess a whole directory + write manifest.json")
    p_bundle.add_argument("--input-dir", required=True, type=Path)
    p_bundle.add_argument("--output-dir", required=True, type=Path)
    p_bundle.add_argument("--batch-id", required=True)
    p_bundle.add_argument("--tenant-id", default="sd-default")
    p_bundle.add_argument("--datastructure-dir", type=Path, default=None)
    p_bundle.add_argument("--force", action="store_true")
    p_bundle.set_defaults(func=cmd_bundle)

    p_verify = sub.add_parser("verify", help="Re-validate emitted manifest.json against files")
    p_verify.add_argument("--batch-dir", required=True, type=Path)
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return int(args.func(args))


def cmd_postprocess(args: argparse.Namespace) -> int:
    config = load_redaction_config(args.datastructure_dir)
    schema = _schema_from_filename(args.input.name)
    result = postprocess_dump(args.input, args.output, schema, config)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.force:
        print(
            f"FATAL: output_dir {args.output_dir} is non-empty; pass --force to overwrite",
            file=sys.stderr,
        )
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = load_redaction_config(args.datastructure_dir)
    files: list[dict[str, Any]] = []
    redaction_summary: dict[str, int] = defaultdict(int)
    total_rows = 0
    for src in sorted(args.input_dir.glob("dump-*.sql")):
        schema = _schema_from_filename(src.name)
        dst = args.output_dir / src.name
        result = postprocess_dump(src, dst, schema, config)
        files.append(result)
        total_rows += result["rowcount"]
        for kind, n in result["redaction_counts"].items():
            redaction_summary[kind] += n
    manifest = {
        "batch_id": args.batch_id,
        "tenant_id": args.tenant_id,
        "generated_at": _utcnow_iso(),
        "schema_count": len({f["schema"] for f in files}),
        "file_count": len(files),
        "total_rows": total_rows,
        "redaction_summary": dict(redaction_summary),
        "files": files,
        "redaction_config_source": str(args.datastructure_dir)
        if args.datastructure_dir
        else "<repo>/old/12-datastructure",
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "file_count": len(files), "total_rows": total_rows}))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    manifest_path = args.batch_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"FATAL: manifest.json not found in {args.batch_dir}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for entry in manifest["files"]:
        dump_path = args.batch_dir / entry["filename"]
        if not dump_path.is_file():
            failures.append(f"missing file: {entry['filename']}")
            continue
        observed_crc = _crc32_hex(dump_path)
        observed_sha = _sha256_hex(dump_path)
        if observed_crc != entry["crc32"]:
            failures.append(f"crc32 mismatch: {entry['filename']}")
        if observed_sha != entry["sha256"]:
            failures.append(f"sha256 mismatch: {entry['filename']}")
    report = {
        "batch_id": manifest["batch_id"],
        "ok": not failures,
        "file_count": len(manifest["files"]),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not failures else 1


def postprocess_dump(src: Path, dst: Path, schema: str, config: RedactionConfig) -> dict[str, Any]:
    """Stream src → dst, redacting sensitive values; return per-file stats."""
    redaction_counts: dict[str, int] = defaultdict(int)
    rowcount = 0
    # First pass: learn column order per table (mysqldump streaming parser).
    columns_by_table = _columns_by_table(src)
    with src.open("r", encoding="utf-8", errors="replace") as fin, dst.open(
        "w", encoding="utf-8", newline="\n"
    ) as fout:
        for raw_line in fin:
            line = raw_line.rstrip("\r\n")
            m = INSERT_LINE_RE.match(line)
            if m is None:
                fout.write(raw_line)
                continue
            table = m.group(1)
            columns = columns_by_table.get(table)
            if not columns:
                # No CREATE TABLE seen — keep original line, do not redact blindly.
                fout.write(raw_line)
                continue
            payload = m.group(2)
            new_payload, table_row_count, table_redactions = _rewrite_values(
                schema, table, columns, payload, config
            )
            rowcount += table_row_count
            for k, v in table_redactions.items():
                redaction_counts[k] += v
            fout.write(f"INSERT INTO `{table}` VALUES {new_payload};\n")
    crc = _crc32_hex(dst)
    sha = _sha256_hex(dst)
    (dst.with_suffix(dst.suffix + ".crc")).write_text(crc + "\n", encoding="utf-8")
    (dst.with_suffix(dst.suffix + ".rowcount")).write_text(str(rowcount) + "\n", encoding="utf-8")
    return {
        "filename": dst.name,
        "schema": schema,
        "rowcount": rowcount,
        "crc32": crc,
        "sha256": sha,
        "redaction_counts": dict(redaction_counts),
        "bytes": dst.stat().st_size,
    }


def _columns_by_table(src: Path) -> dict[str, list[str]]:
    """One-shot parse to learn column order for every table in the dump."""
    parser = MysqldumpParser(src)
    # Force one drain — the parser builds columns_by_table during the scan.
    for _ in parser.iter_rows():
        break
    # The parser learns columns as CREATE TABLE blocks are seen; one row isn't
    # enough if INSERT statements come before all CREATE TABLEs. Do a full
    # streaming pass that only reads headers.
    columns: dict[str, list[str]] = {}
    current = None
    column_def_re = re.compile(r"^\s*`([^`]+)`\s")
    create_open_re = re.compile(r"^CREATE TABLE `([^`]+)` \($")
    with src.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if current is not None:
                if line.startswith(")"):
                    current = None
                    continue
                cm = column_def_re.match(line)
                if cm:
                    columns.setdefault(current, []).append(cm.group(1))
                continue
            om = create_open_re.match(line)
            if om:
                current = om.group(1)
                columns.setdefault(current, [])
    return columns


def _rewrite_values(
    schema: str,
    table: str,
    columns: list[str],
    payload: str,
    config: RedactionConfig,
) -> tuple[str, int, dict[str, int]]:
    """Re-serialize a VALUES payload with sensitive columns masked."""
    # Determine which column indexes need redaction.
    column_decisions = [config.decide(schema, table, col) for col in columns]
    target_idx = [i for i, d in enumerate(column_decisions) if d.redact]
    if not target_idx:
        # Fast path: nothing to redact in this table; just count rows.
        return payload, _count_value_tuples(payload), {}
    # Slow path: parse + re-emit row by row.
    from zw_brain.adapters.legacy.parser import _iter_value_tuples  # noqa: PLC0415 — internal reuse

    pieces: list[str] = []
    row_count = 0
    redaction_counts: dict[str, int] = defaultdict(int)
    for row_tuple in _iter_value_tuples(payload):
        if len(row_tuple) != len(columns):
            # Malformed row — emit verbatim, do not redact wrong columns.
            pieces.append(_emit_tuple(row_tuple))
            row_count += 1
            continue
        new_row = list(row_tuple)
        for i in target_idx:
            decision = column_decisions[i]
            new_row[i] = mask_value(columns[i], new_row[i], decision)
            redaction_counts[decision.kind] += 1
        pieces.append(_emit_tuple(new_row))
        row_count += 1
    return ",".join(pieces), row_count, dict(redaction_counts)


def _count_value_tuples(payload: str) -> int:
    from zw_brain.adapters.legacy.parser import _iter_value_tuples  # noqa: PLC0415 — internal reuse

    return sum(1 for _ in _iter_value_tuples(payload))


def _emit_tuple(row: list[Any]) -> str:
    parts = [_emit_scalar(v) for v in row]
    return "(" + ",".join(parts) + ")"


def _emit_scalar(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    s = (
        s.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\0", "\\0")
    )
    return f"'{s}'"


def _crc32_hex(path: Path) -> str:
    crc = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 16)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    return f"{crc & 0xFFFFFFFF:08x}"


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 16)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _schema_from_filename(name: str) -> str:
    m = DUMP_NAME_RE.match(name)
    if m:
        return m.group(1)
    # Best-effort fallback: strip `dump-` and `.sql`
    return name.removeprefix("dump-").removesuffix(".sql").rsplit("-", 1)[0]


def _utcnow_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
