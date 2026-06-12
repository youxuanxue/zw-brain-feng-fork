#!/usr/bin/env python3
"""check_no_numbered_routes.py — preflight 段 21

强约束（路由去编号化落地后的防回潮）：
    前端 SPA 路由必须用纯语义路径（如 `#/compliance-ops`），禁止 IA 编号烙进 URL。
    曾经的 P0–P8 编号化（`#/p0-…` ~ `#/p8-…`）已在 commit f10f989 / df93a2d 整体退役。

    此检查扫描以下文件，禁止任何 `#/p[0-9]+-` 形式路由再次出现：
      - zw-brain-web/js/*.js
      - zw-brain-web/*.html
      - zw_brain/**/*.py（后端 todo href / 测试断言等）
      - tests/**/*.py
      - scripts/**/*.py / *.sh
      - docs/deployment/**/*.md（客户交付路径示例）

允许例外：
      - 本脚本自身（含 anti-pattern 字面示例）
      - docs/preflight-debt.md 的历史 entry（如果未来重新出现）
      - old/ / .legacy_cache/（旧平台真实数据）

退出码：0 = 全部通过；1 = 至少一处违反

使用：
    ./scripts/check_no_numbered_routes.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EXTENSIONS = (".py", ".js", ".html", ".sh", ".md")

SKIP_PATH_FRAGMENTS = (
    "/.venv/",
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/.claude/worktrees/",
    "/.data/",
    "/.reviews/",
    "/old/",
    "/.legacy_cache/",
    "/dist/",
    "/build/",
    "/.testing/",
)

ALLOWED_FILES = (
    "scripts/check_no_numbered_routes.py",  # 本脚本自身（含示例字面值）
    "docs/preflight-debt.md",  # 历史 entry 可能引用
)

PATTERN = re.compile(r"#/p[0-9]+-[a-z]")  # `#/p<N>-<letter>` 形式编号化路由


def scan_file(path: Path) -> list[tuple[int, str]]:
    rel = str(path.relative_to(REPO))
    if rel in ALLOWED_FILES:
        return []
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if PATTERN.search(line):
            hits.append((lineno, line.strip()))
    return hits


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    scanned = 0
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        # 相对路径匹配（同 check_no_legacy_role_codes.should_skip_path）：仓库根在
        # worktree 副本下时，绝对路径匹配会把全仓误跳过（本地假绿）。
        if any(frag in f"/{path.relative_to(REPO).as_posix()}" for frag in SKIP_PATH_FRAGMENTS):
            continue
        if path.suffix not in EXTENSIONS:
            continue
        scanned += 1
        for lineno, line in scan_file(path):
            violations.append((str(path.relative_to(REPO)), lineno, line))

    if violations:
        print(f"[no-numbered-routes] FAIL: {len(violations)} numbered-route hit(s):")
        for fp, lineno, line in violations[:30]:
            print(f"  {fp}:{lineno}  {line[:120]}")
        if len(violations) > 30:
            print(f"  ... and {len(violations) - 30} more")
        print()
        print("路由去编号化基线：URL 必须用纯语义路径（#/compliance-ops 而非 #/p6-compliance-ops）。")
        print("理由：编号化是反模式 — IA 一动就全栈改、新增页无处插、URL 对用户不透明。")
        return 1

    print(f"[no-numbered-routes] ok: scanned {scanned} files; no #/p<N>- numbered route residue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
