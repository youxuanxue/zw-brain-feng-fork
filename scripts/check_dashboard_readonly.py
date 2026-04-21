#!/usr/bin/env python3
"""
check_dashboard_readonly.py — preflight 段 11

强约束（设计基线 §十四 D15）：
    `zw-brain-dashboard/` 子项目**只读消费 dashboard.* Skill**——禁止内嵌
    任何写操作（DB write / mutation Skill 调用 / 状态变更 HTTP 方法）。
    架构上保持相对独立：故障与主大脑隔离，写操作 leak 进 dashboard 即破坏
    隔离前提。

扫描黑名单：
    1. HTTP mutation 方法字面量：POST / PUT / PATCH / DELETE
       （在 axios / fetch / requests 调用中）
    2. ORM 写操作：session.add / session.commit / session.delete /
       db.execute INSERT|UPDATE|DELETE
    3. mutation Skill 调用：以 `.create(`/`.update(`/`.delete(`/`.submit(`/
       `.approve(`/`.reject(` 等 verb 后缀的 SDK 调用
    4. 全局允许的只读 Skill 命名：以 `dashboard.` / `query.` / `read.` / `get_` 开头

扫描范围：
    `zw-brain-dashboard/` 子项目内的 .py / .ts / .tsx / .js / .jsx / .vue
    文件；不存在时 skip + exit 0（Phase 0 早期）。

接入：scripts/preflight.sh 段 11
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DASHBOARD_DIR = "zw-brain-dashboard"

# JS/TS/Vue: axios.post / fetch(url, {method: 'POST'}) / $http.put 等
HTTP_MUTATION_PATTERNS = [
    re.compile(r"""\b(?:axios|fetch|http|\$http|api|client)\s*\.\s*(post|put|patch|delete)\s*\(""", re.IGNORECASE),
    re.compile(r"""method\s*:\s*['"](?:POST|PUT|PATCH|DELETE)['"]""", re.IGNORECASE),
    re.compile(r"""@(?:Post|Put|Patch|Delete)Mapping\b"""),  # Java/Spring style
]

# Python: SQLAlchemy / SQL DML
PY_WRITE_PATTERNS = [
    re.compile(r"""\bsession\s*\.\s*(add|commit|delete|merge|flush)\s*\("""),
    re.compile(r"""\bdb\s*\.\s*(execute|executemany)\s*\(\s*['"](?:\s*)(INSERT|UPDATE|DELETE)\b""", re.IGNORECASE),
    re.compile(r"""\.\s*(create_all|drop_all)\s*\("""),  # SQLAlchemy schema mutation
]

# Skill 调用动词后缀（mutation hint）
# 不放 `.write(` —— 太宽泛，会误命中 wfile.write / sys.stdout.write / Logger.write
# 等纯 I/O；真实 Skill 写操作通常采用 .save( / .create( / .submit( 等更明确的动词。
SKILL_MUTATION_SUFFIXES = (
    ".create(",
    ".update(",
    ".delete(",
    ".submit(",
    ".approve(",
    ".reject(",
    ".save(",
    ".remove(",
    ".cancel(",
    ".publish(",
    ".unpublish(",
)

# 注释标记 — 显式豁免（可信 review 后允许）
EXEMPT_MARKER = "# dashboard-readonly: ignore"

TARGET_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".java", ".kt"}


_PY_LINE_COMMENT = re.compile(r"^\s*#")
_JS_LINE_COMMENT = re.compile(r"^\s*//")
_JS_BLOCK_COMMENT = re.compile(r"^\s*\*")  # JSDoc / block-comment continuation lines
_JS_DOCSTRING_OPEN = re.compile(r"^\s*/\*")
_JS_DOCSTRING_CLOSE = re.compile(r"\*/\s*$")
_PY_TRIPLE_QUOTE = re.compile(r'(?:"""|\'\'\')')


def _is_pure_comment_line(line: str, ext: str, in_block_comment: bool) -> tuple[bool, bool]:
    """Return (skip_this_line, new_in_block_comment_state).

    Strips lines that are pure comments / docstring continuations so the
    mutation patterns don't match prose. We deliberately do NOT try to do
    full lexical analysis — false positives are caught by the EXEMPT_MARKER.
    """
    if ext in {".py"}:
        if _PY_LINE_COMMENT.match(line):
            return True, in_block_comment
        return False, in_block_comment
    # JS / TS / Vue / Java / Kotlin
    if in_block_comment:
        if _JS_DOCSTRING_CLOSE.search(line):
            return True, False
        return True, True
    if _JS_DOCSTRING_OPEN.match(line):
        if _JS_DOCSTRING_CLOSE.search(line):
            return True, False
        return True, True
    if _JS_LINE_COMMENT.match(line) or _JS_BLOCK_COMMENT.match(line):
        return True, False
    return False, False


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations

    ext = path.suffix
    in_block_comment = False
    in_py_docstring = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        if EXEMPT_MARKER in line:
            continue

        # crude Python triple-quoted string toggle (skips docstring bodies)
        if ext == ".py":
            tq_count = len(_PY_TRIPLE_QUOTE.findall(line))
            if tq_count % 2 == 1:
                in_py_docstring = not in_py_docstring
                continue
            if in_py_docstring:
                continue

        skip, in_block_comment = _is_pure_comment_line(line, ext, in_block_comment)
        if skip:
            continue

        for pat in HTTP_MUTATION_PATTERNS:
            if pat.search(line):
                violations.append((lineno, "HTTP_MUTATION", line.strip()[:120]))
                break
        else:
            for pat in PY_WRITE_PATTERNS:
                if pat.search(line):
                    violations.append((lineno, "DB_WRITE", line.strip()[:120]))
                    break
            else:
                for suffix in SKILL_MUTATION_SUFFIXES:
                    if suffix in line:
                        violations.append((lineno, "MUTATION_SKILL_CALL", line.strip()[:120]))
                        break
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    dash = repo_root / DASHBOARD_DIR
    if not dash.exists():
        print(f"[dashboard-readonly] skip: {DASHBOARD_DIR}/ not yet created (Phase 0 task)")
        print("  (this check becomes enforcing once Phase 0 creates the dashboard skeleton)")
        return 0

    total_files = 0
    total_violations = 0

    for path in dash.rglob("*"):
        if not path.is_file() or path.suffix not in TARGET_EXTS:
            continue
        # 跳过 node_modules / dist / build 等构建产物
        rel = path.relative_to(repo_root)
        rel_str = str(rel).replace("\\", "/")
        if any(seg in rel_str for seg in ("/node_modules/", "/dist/", "/build/", "/.next/", "/__pycache__/")):
            continue
        total_files += 1
        violations = scan_file(path)
        if violations:
            total_violations += len(violations)
            print(f"\n  ✗ {rel}")
            for lineno, kind, snippet in violations:
                print(f"      L{lineno} [{kind}] {snippet}")

    print()
    if total_violations == 0:
        print(f"[dashboard-readonly] OK: scanned {total_files} files in {DASHBOARD_DIR}/, no write operations detected")
        return 0
    print(f"[dashboard-readonly] FAIL: {total_violations} write operation(s) detected in {DASHBOARD_DIR}/")
    print("  policy (D15): dashboard MUST be read-only consumer of dashboard.* Skills")
    print("  fix: remove the write operation, or move it to a non-dashboard subproject")
    print(f"  exempt marker (use sparingly with review): {EXEMPT_MARKER}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
