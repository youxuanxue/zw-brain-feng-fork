#!/usr/bin/env python3
"""
check_external_refs.py
======================

外部文档引用悬空检查（preflight 段 14）。

规则来源（D22 retrofit）:
    zw-brain 多处文档引用 `digital-clone-research.md §X`（workspace 同级路径，
    .gitignore'd 不入库）。该文件曾被物理删除而所有引用悄无声息腐烂，且 stat
    `hard-constraint-rows` 因 `|| true` 静默吞错被误报"OK"。本脚本机械化阻止
    此类「引用了仓外文件但不验证文件存在 / 锚点存在」的反模式重发。

判定逻辑：
    扫描 zw-brain 仓内所有 *.md / *.mdc 文件（排除 dev-rules submodule、prototype
    子模块状态目录、.git 目录、old/ 目录、.cursor/rules/ 同步产物镜像），抽取所有
    `digital-clone-research.md §X` 形式的引用：
      1. 仓库根 `../../digital-clone-research.md` 文件必须存在
      2. 引用的 §X 标题（无论是 §六.½ §七 §九.1 还是 §11.3）必须在该文件中真实出现
    缺任一条 → exit 1。

豁免：
    无（外部引用必须验证；如果某引用无法验证，应当本地化为 zw-brain 内部引用 = B 路径）。

设计取舍（Jobs/OPC）：
    - **Jobs**: 只检查一种已知形态（`digital-clone-research.md §X`），不做通用「任何
      文件路径引用都验证」（rabbit hole；幽灵引用检查由 dev-rules/verify-rules.sh
      段 6 在子模块层覆盖）。
    - **OPC**: 引用与目标文件之间的"对齐"是变更必伴漂移的典型场景，必须机械检查。

接入：scripts/preflight.sh 段 14
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_FILE = REPO_ROOT.parent.parent / "digital-clone-research.md"

# zw-brain 仓内待扫描的目录
SCAN_ROOTS = [
    REPO_ROOT / "docs",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / ".cursor" / "rules",
]

# 排除：dev-rules submodule（独立仓库，自有 verify-rules.sh）；old/（历史素材，不入库）；
# prototype/（UI 资源没有外部引用）；.testing/（fixture）；node_modules / .git 自动跳过
EXCLUDE_PATH_PARTS = {".git", "node_modules", "old", "dev-rules", "prototype", ".testing"}

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


def collect_external_anchors() -> set[str] | None:
    """Parse all '## §X' style headings from the external file. Return None if file missing."""
    if not EXTERNAL_FILE.exists():
        return None
    text = EXTERNAL_FILE.read_text(encoding="utf-8")
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

    anchors = collect_external_anchors()
    if anchors is None:
        print(
            f"[external-refs] FAIL: external file missing\n"
            f"  expected at: {EXTERNAL_FILE}\n"
            f"  but {sum(len(v) for v in refs.values())} reference(s) across {len({f for v in refs.values() for f, _ in v})} file(s) point to it.\n"
            f"  fix: restore the file (see ~/Backups/zw-brain-pre-rewrite-2026-04-18.git for blob `2ea4f60:digital-clone-research.md`),\n"
            f"       OR localize the references into zw-brain (see docs/approved/zw-brain-architecture.md 附录 B).",
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
            f"  external file: {EXTERNAL_FILE}\n"
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
