#!/usr/bin/env python3
"""migrate_debt_to_function — one-time转换 docs/preflight-debt.md → .testing/debt/*.debt.yaml.

Parses each `## YYYY-MM-DD — title` block and emits a skeleton .debt.yaml carrying
title/date/severity + a placeholder `external` assert (owner left TODO, trigger
lifted from the block's **Trigger** line when present). The asserts are then
hand-upgraded per entry (grep_present / grep_absent / script) where a code
condition exists; entries with no code condition stay `external` with a real owner.

One-shot: run once, hand-tune the produced yamls, then retire preflight-debt.md to a
pointer. Re-running NEVER clobbers files that already exist (so hand-tuning is safe).
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "preflight-debt.md"
DEBT_DIR = REPO_ROOT / ".testing" / "debt"


def slugify(title: str, date: str) -> str:
    title = re.sub(r"\*\*.*?\*\*", "", title).strip()
    m = re.search(r"[A-Za-z][A-Za-z0-9_.\-]{2,}", title)
    if m:
        base = m.group(0).lower().replace(".", "-").replace("_", "-")
        return re.sub(r"-+", "-", base).strip("-")
    return "debt-" + hashlib.sha1(f"{date}:{title}".encode()).hexdigest()[:8]  # noqa: S324


def parse_entries(text: str) -> list[dict]:
    blocks = re.split(r"(?m)^(?=##\s+\d{4}-\d{2}-\d{2}\s+—)", text)
    out: list[dict] = []
    seen: set[str] = set()
    for b in blocks:
        m = re.match(r"##\s+(\d{4}-\d{2}-\d{2})\s+—\s+(.+)", b)
        if not m:
            continue
        date, title = m.group(1), m.group(2).strip()
        trig = re.search(r"\*\*Trigger[^*]*\*\*[:：]\s*(.+)", b)
        trigger = (trig.group(1).strip() if trig else "见 docs/preflight-debt.md 历史归档").rstrip(".。")
        slug = slugify(title, date)
        base, n = slug, 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        seen.add(slug)
        out.append({"slug": slug, "date": date, "title": title, "trigger": trigger})
    return out


def yq(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def render_skeleton(entry: dict) -> str:
    return (
        f"slug: {entry['slug']}\n"
        f"title: {yq(entry['title'])}\n"
        f"date: {entry['date']}\n"
        f"severity: medium\n"
        f"owner: TODO-补业务/技术 owner\n"
        f"trigger: {yq(entry['trigger'])}\n"
        f"assert:\n"
        f"  # TODO: 有 code 条件改 grep_present/grep_absent/script；无则保持 external（须 owner+trigger）。\n"
        f"  kind: external\n"
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"[migrate-debt] source absent: {SOURCE}", file=sys.stderr)
        return 1
    DEBT_DIR.mkdir(parents=True, exist_ok=True)
    entries = parse_entries(SOURCE.read_text(encoding="utf-8"))
    written = skipped = 0
    for e in entries:
        path = DEBT_DIR / f"{e['slug']}.debt.yaml"
        if path.exists():
            skipped += 1
            continue
        path.write_text(render_skeleton(e), encoding="utf-8")
        written += 1
    print(f"[migrate-debt] parsed {len(entries)}; wrote {written}, skipped {skipped} (already exist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
