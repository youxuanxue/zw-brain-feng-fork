#!/usr/bin/env python3
"""
check_gate1_prototype.py
========================

GATE-1 原型覆盖检查（preflight 段 13）。

规则来源：
    `product-dev.mdc` 阶段 2 「原型设计与实现」明确要求设计文档（写入
    `docs/approved/`）必须配套「最小可运行原型」。本脚本机械化阻止
    「设计已 approved 但原型缺失」的反复发生。

判定逻辑：
    扫描 docs/approved/*.md，对每份 status: approved 的设计文档：
      1. 必须存在 prototype/README.md
      2. prototype/README.md 必须含「验证 checklist」段（关键词检测）
      3. 必须存在 prototype/storyboards/ 且至少 1 份 *.md
      4. 必须存在 prototype/ui/index.html（真 UI 入口）
    缺任一条 → exit 1。

豁免：
    设计文档 frontmatter 中显式标注 `prototype: not-required` 才豁免
    （需在 PR 描述中说明理由 + 至少 1 名 reviewer 同意）。

接入：scripts/preflight.sh 段 13
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPROVED_DIR = REPO_ROOT / "docs" / "approved"
PROTOTYPE_DIR = REPO_ROOT / "prototype"

REQUIRED_FILES = {
    "README":        PROTOTYPE_DIR / "README.md",
    "ui_entry":      PROTOTYPE_DIR / "ui" / "index.html",
    "storyboards":   PROTOTYPE_DIR / "storyboards",  # 目录
}

CHECKLIST_KEYWORDS = [
    "验证 checklist",
    "评审 checklist",
    "验证清单",
    "评审清单",
    "verification checklist",
    "review checklist",
]


def extract_frontmatter(text: str) -> dict:
    """提取 YAML frontmatter 中的关键字段（不引入 yaml 依赖）。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^\s*([A-Za-z_][\w-]*)\s*:\s*(.+?)\s*$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def scan_approved_docs() -> list[tuple[Path, dict]]:
    """返回 [(path, frontmatter_dict), ...]，仅包括 status: approved 的文档。"""
    if not APPROVED_DIR.exists():
        return []
    out = []
    for md in sorted(APPROVED_DIR.glob("*.md")):
        fm = extract_frontmatter(md.read_text(encoding="utf-8"))
        if fm.get("status") == "approved":
            out.append((md, fm))
    return out


def check_one(doc_path: Path, fm: dict) -> list[str]:
    errors: list[str] = []
    if fm.get("prototype") == "not-required":
        return []  # 豁免

    # 1. README 存在
    readme = REQUIRED_FILES["README"]
    if not readme.exists():
        errors.append(f"missing prototype/README.md (required by {doc_path.name})")
    else:
        body = readme.read_text(encoding="utf-8")
        if not any(kw in body for kw in CHECKLIST_KEYWORDS):
            errors.append(
                f"prototype/README.md missing 「验证 checklist」 section "
                f"(keywords expected: {CHECKLIST_KEYWORDS})"
            )

    # 2. UI 入口存在
    ui = REQUIRED_FILES["ui_entry"]
    if not ui.exists():
        errors.append(f"missing prototype/ui/index.html (required by {doc_path.name})")

    # 3. storyboards 目录非空
    sb_dir = REQUIRED_FILES["storyboards"]
    if not sb_dir.is_dir():
        errors.append(f"missing prototype/storyboards/ directory (required by {doc_path.name})")
    else:
        sb_files = list(sb_dir.glob("*.md"))
        if not sb_files:
            errors.append(f"prototype/storyboards/ contains no *.md (required by {doc_path.name})")

    return errors


def main() -> int:
    docs = scan_approved_docs()
    if not docs:
        print("[gate1-prototype] skip: no docs/approved/*.md with status: approved found")
        return 0

    all_errors: list[str] = []
    for doc, fm in docs:
        errs = check_one(doc, fm)
        if errs:
            all_errors.extend([f"  · [{doc.name}] {e}" for e in errs])

    if all_errors:
        print("[gate1-prototype] FAIL: GATE-1 prototype coverage missing")
        for e in all_errors:
            print(e)
        print()
        print("  Why this matters:")
        print("    product-dev.mdc 阶段 2 明确要求 docs/approved/ 中的设计文档")
        print("    必须配套「可启动、可演示核心流程」的最小原型。这是 GATE-1")
        print("    人工审批的物质基础，不能仅审文档。")
        print()
        print("  How to fix:")
        print("    A. 补做原型（推荐）— 至少包含：")
        print("       prototype/README.md（含「验证 checklist」段）")
        print("       prototype/ui/index.html（真 UI 入口）")
        print("       prototype/storyboards/*.md（至少 1 份场景叙事）")
        print("    B. 在该 design 文档 frontmatter 中加 `prototype: not-required` 并说明理由")
        return 1

    print(f"[gate1-prototype] OK: {len(docs)} approved design doc(s) all have prototype coverage")
    return 0


if __name__ == "__main__":
    sys.exit(main())
