#!/usr/bin/env python3
"""
check_external_refs.py
======================

外部文档引用悬空检查（preflight 段 14）。

规则来源（D22 retrofit）:
    仓内 `docs/`、`CLAUDE.md`、`.cursor/rules/` 若写 `digital-clone-research.md §X`，
    则 § 锚点必须在**权威对照文件**中真实存在，否则 exit 1。本检查在**零引用**时直接通过。

权威对照文件（按优先级）:
    1. 环境变量 `DIGITAL_CLONE_RESEARCH_PATH`（若指向可读文件）
    2. `dev-rules/digital-clone-research.md`（本机可选 symlink / 克隆）
    3. `docs/approved/zw-brain-architecture.md`（zw-brain 自包含基线，含 §一/二/三 等章节结构）

判定逻辑：
    抽取 `digital-clone-research.md §X` 形态引用，与对照文件内 `## …` 风格标题中的
    节号对齐（与既有锚点归一化规则一致）。

豁免：
    无（若重新引入此类引用，则必须恢复外部文件且锚点可解析，或改回本地化表述）。

设计取舍（Jobs/OPC）：
    - **Jobs**: 只检查一种已知形态（`digital-clone-research.md §X`），不做通用「任何
      文件路径引用都验证」（rabbit hole；幽灵引用检查由 dev-rules/verify-rules.sh
      段 6 在子模块层覆盖）。
    - **OPC**: 引用与目标文件之间的"对齐"是变更必伴漂移的典型场景，必须机械检查。

接入：scripts/preflight.sh 段 14
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_external_file() -> Path:
    """Prefer standalone research doc; fall back to shipped v4 baseline (no dev-rules required)."""
    env = os.environ.get("DIGITAL_CLONE_RESEARCH_PATH", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
    for rel in (
        Path("dev-rules") / "digital-clone-research.md",
        Path("docs") / "approved" / "zw-brain-architecture.md",
    ):
        p = REPO_ROOT / rel
        if p.is_file():
            return p
    return REPO_ROOT / "dev-rules" / "digital-clone-research.md"

# zw-brain 仓内待扫描的目录
SCAN_ROOTS = [
    REPO_ROOT / "docs",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / ".cursor" / "rules",
]

# 排除：dev-rules submodule（独立仓库，自有 verify-rules.sh）；old/（历史素材，不入库）；
# .testing/（fixture）；node_modules / .git 自动跳过
EXCLUDE_PATH_PARTS = {".git", "node_modules", "old", "dev-rules", ".testing"}

# 引用模式：捕获 §X 标识符（中文 + 数字 + 罗马 + 半角点 + 斜杠等）
# - 形态 1：digital-clone-research.md §六.½  / digital-clone-research §六.½
# - 形态 2：digital-clone-research.md §六.¾
# - 形态 3：digital-clone-research §8 / §9 / §11.3
REF_PATTERN = re.compile(
    r"digital-clone-research(?:\.md)?\s*(?:的\s*)?(?:Phase\s*\d+\s*\(?参照\)?)?\s*"
    r"§\s*([一二三四五六七八九十〇零\d]+(?:[.\u00bd\u00be\u00bc\d]\d*)*)"
)


def collect_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in {".md", ".mdc"}:
                continue
            if any(part in EXCLUDE_PATH_PARTS for part in p.parts):
                continue
            files.append(p)
    return files


def extract_refs(files: list[Path]) -> dict[str, list[tuple[Path, int]]]:
    """Return {anchor_id: [(file, line_no), ...]} for every reference found."""
    refs: dict[str, list[tuple[Path, int]]] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in REF_PATTERN.finditer(line):
                anchor = match.group(1).strip()
                refs.setdefault(anchor, []).append((f, line_no))
    return refs


def collect_external_anchors(path: Path) -> set[str] | None:
    """Parse section ids from '## …' style headings. Return None if file missing."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    anchors: set[str] = set()
    # Heading pattern: '## 六.½ ...', '### 9.1 ...', '## 七、...', '### 3.1 ...'
    head_pat = re.compile(r"^#{2,4}\s+([一二三四五六七八九十〇零\d]+(?:[.\u00bd\u00be\u00bc\d]\d*)*)")
    for line in text.splitlines():
        m = head_pat.match(line)
        if m:
            anchors.add(m.group(1).strip())
    return anchors


def normalize_anchor(a: str) -> str:
    """Normalize trailing dots / fullwidth digits etc. for matching."""
    return a.replace("．", ".").strip(".")


def main() -> int:
    files = collect_files()
    refs = extract_refs(files)

    if not refs:
        print("[external-refs] OK: no `digital-clone-research.md §X` references found in scanned scope")
        return 0

    external_path = resolve_external_file()
    anchors = collect_external_anchors(external_path)
    if anchors is None:
        print(
            f"[external-refs] FAIL: external file missing\n"
            f"  tried: {external_path}\n"
            f"  but {sum(len(v) for v in refs.values())} reference(s) across {len({f for v in refs.values() for f, _ in v})} file(s) point to it.\n"
            f"  fix: add dev-rules mirror + digital-clone-research.md, set DIGITAL_CLONE_RESEARCH_PATH, "
            f"or ensure docs/approved/zw-brain-architecture.md exists; align § anchors.",
            file=sys.stderr,
        )
        return 1

    norm_anchors = {normalize_anchor(a) for a in anchors}
    missing: list[tuple[str, list[tuple[Path, int]]]] = []
    for anchor, sites in refs.items():
        if normalize_anchor(anchor) not in norm_anchors:
            missing.append((anchor, sites))

    if missing:
        print(
            f"[external-refs] FAIL: {len(missing)} anchor(s) referenced but not found in external file:",
            file=sys.stderr,
        )
        for anchor, sites in missing:
            print(f"  §{anchor}", file=sys.stderr)
            for f, line in sites:
                rel = f.relative_to(REPO_ROOT)
                print(f"    - {rel}:{line}", file=sys.stderr)
        print(
            f"  external file: {external_path}\n"
            f"  available anchors: {sorted(norm_anchors)}\n"
            f"  fix: correct the §X label, or update the external file.",
            file=sys.stderr,
        )
        return 1

    total_refs = sum(len(v) for v in refs.values())
    print(
        f"[external-refs] OK: all {total_refs} `digital-clone-research.md §X` reference(s) "
        f"({len(refs)} unique anchor(s)) resolve in external file"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
