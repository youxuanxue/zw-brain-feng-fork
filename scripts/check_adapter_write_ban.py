#!/usr/bin/env python3
"""check_adapter_write_ban.py — preflight 段 25

§9.5 / 附录 C：adapter 禁止成为新写入口。

zw-brain 的 adapter 只负责"读 legacy 数据 + 一次性迁移"。当前唯一合法写区是
`zw_brain/adapters/legacy/`（迁移 mapper / migration_batch / runner）；任何 *其它*
adapter 子目录出现 SQLAlchemy `session.add` / `session.commit` / `.merge(` /
`.flush(` 等写 token，都视为新业务写入口的复活迹象。

规则：
    - 允许：`zw_brain/adapters/legacy/**/*.py` —— 一次性迁移写
    - 允许：显式行级豁免标注 `# adapter-write-ok:` 后跟理由
    - 禁止：`zw_brain/adapters/` 下其它任何路径出现写 token

退出码：0 = 全部通过；1 = 至少一处违规
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADAPTERS_DIR = REPO / "zw_brain" / "adapters"

# 合法写区（一次性迁移）
ALLOWED_WRITE_ZONES = (
    "zw_brain/adapters/legacy",
)

# SQLAlchemy / 裸 SQL 写 token
WRITE_TOKENS = (
    re.compile(r"\bsession\.add\b"),
    re.compile(r"\bsession\.add_all\b"),
    re.compile(r"\bsession\.commit\b"),
    re.compile(r"\bsession\.merge\b"),
    re.compile(r"\bsession\.delete\b"),
    re.compile(r"\bsession\.flush\b"),
    re.compile(r"\bsession\.execute\([^)]*\b(insert|update|delete)\b", re.IGNORECASE),
    re.compile(r"\b(?:INSERT|UPDATE|DELETE)\s+(?:INTO|FROM|\w+\s+SET)\b", re.IGNORECASE),
)

# 行级豁免：注释里有 "# adapter-write-ok: <reason>" 整行豁免
LINE_EXEMPT = re.compile(r"#\s*adapter-write-ok:")


def is_in_allowed_zone(rel_path: str) -> bool:
    for zone in ALLOWED_WRITE_ZONES:
        if rel_path.startswith(zone + "/") or rel_path == zone:
            return True
    return False


def scan_file(path: Path) -> list[str]:
    rel = path.relative_to(REPO).as_posix()
    if is_in_allowed_zone(rel):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if LINE_EXEMPT.search(line):
            continue
        for pat in WRITE_TOKENS:
            m = pat.search(line)
            if m:
                snippet = stripped[:120]
                findings.append(
                    f"{rel}:{lineno}: 禁区出现写 token `{m.group(0)}` → `{snippet}`"
                )
                break
    return findings


def main() -> int:
    if not ADAPTERS_DIR.exists():
        print(f"[skip] {ADAPTERS_DIR} 不存在", file=sys.stderr)
        return 0
    findings: list[str] = []
    for path in sorted(ADAPTERS_DIR.rglob("*.py")):
        findings.extend(scan_file(path))
    if findings:
        print("§9.5 adapter 写禁区违规：", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print(
            f"\n共 {len(findings)} 处违规。"
            f"\n合法写区仅限：{', '.join(ALLOWED_WRITE_ZONES)}/"
            f"\n若确实是一次性迁移路径，请将文件移入合法写区；"
            f"\n若是真新业务写需求，应通过 command/domain 层落地（违反基线 §9.5）。",
            file=sys.stderr,
        )
        return 1
    print(
        "[OK] adapter 写禁区清洁："
        f"{', '.join(ALLOWED_WRITE_ZONES)}/ 之外无写 token",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
