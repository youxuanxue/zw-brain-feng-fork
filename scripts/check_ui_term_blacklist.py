#!/usr/bin/env python3
"""check_ui_term_blacklist.py — preflight 段 24

R12 工程术语不进 UI 守卫（设计基线 §5.5 / R12）。

扫 zw-brain-web/ 的 .html / .js / .css，确保 9 个黑名单术语不漏入用户可见 UI 文本。

判定模型：
    1. 剥掉所有 ${...} JS 表达式（模板字符串占位符）
    2. 剥掉所有 HTML 属性值 `attr="..."` / `attr='...'`
    3. 剥掉单行注释与块注释
    4. 在剩余文本里查 blacklist 命中——但只有命中**位于含非 ASCII 字符的字符串字面值内**
       才视为 UI 漏出（skill_id slug / 路由 / 标识符都是纯 ASCII，不构成 UI）。
    5. HTML 文件额外扫 `>...<` text content（同一非 ASCII 规则）。

退出码：0 = 全部通过；1 = 至少一处 UI 漏出
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO / "zw-brain-web"

# R12 黑名单（一字不差对照设计基线 §5.5）
BLACKLIST = (
    "package",
    "projection",
    "capability",
    "write-with-audit",
    "register-version",
    "apply-tenant-policy",
    "reconcile-receipt",
    "submit-evidence",
    "policy_decision",
)


def _term_pattern(term: str) -> re.Pattern[str]:
    # hyphen 与 underscore 都视作分隔符
    escaped = re.escape(term).replace(r"\-", r"[-_]")
    return re.compile(escaped, re.IGNORECASE)


BLACKLIST_PATTERNS = [(t, _term_pattern(t)) for t in BLACKLIST]

# 行级豁免（显式标注 + 注释行）
LINE_LEVEL_ALLOWED = (
    "// R12-exempt",
    "/* R12-exempt",
)

# 文件级豁免（生成产物 / 文档 / 测试夹具）
SKIP_PATH_FRAGMENTS = (
    "/node_modules/",
    "/__pycache__/",
    "/.git/",
    "/dist/",
    "/dist-vite/",
    "/build/",
)

EXTENSIONS = (".html", ".js", ".css")


def has_non_ascii(s: str) -> bool:
    return any(ord(c) > 127 for c in s)


def enclosing_string_literal(line: str, pos: int) -> str | None:
    """返回包裹 pos 的字符串字面值（去引号）；不在任何字面值内返回 None。"""
    state: str | None = None
    start = -1
    i = 0
    while i < len(line):
        c = line[i]
        if state is None:
            if c in "'\"`":
                state = c
                start = i
        else:
            if c == "\\":
                i += 2
                continue
            if c == state:
                if start < pos < i:
                    return line[start + 1 : i]
                state = None
                start = -1
        i += 1
    return None


HTML_TEXT_RE = re.compile(r">([^<]+)<")

# 剥掉模板字符串占位符 ${...}（支持嵌套一层），避免把 JS 表达式当 UI
TEMPLATE_EXPR_RE = re.compile(r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
# 剥掉 HTML / JSX 属性值 `attr="..."` / `attr='...'`
HTML_ATTR_RE = re.compile(r"\s[\w:-]+\s*=\s*(['\"])(?:(?!\1).)*\1")


def _strip_noise(line: str) -> str:
    line = TEMPLATE_EXPR_RE.sub(" ", line)
    line = HTML_ATTR_RE.sub(" ", line)
    return line


def scan_js_or_css(line: str) -> list[str]:
    cleaned = _strip_noise(line)
    hits: list[str] = []
    for term, pat in BLACKLIST_PATTERNS:
        for match in pat.finditer(cleaned):
            literal = enclosing_string_literal(cleaned, match.start())
            if literal is not None and has_non_ascii(literal):
                hits.append(term)
                break
    return hits


def scan_html_line(line: str) -> list[str]:
    cleaned = _strip_noise(line)
    hits: list[str] = []
    for term, pat in BLACKLIST_PATTERNS:
        flagged = False
        # 在 `>X<` 之间的 text content 命中
        for chunk_match in HTML_TEXT_RE.finditer(cleaned):
            chunk = chunk_match.group(1)
            if not has_non_ascii(chunk):
                continue
            if pat.search(chunk):
                hits.append(term)
                flagged = True
                break
        if flagged:
            continue
        # 也扫 inline 字符串字面值（剥噪后剩下的）
        for match in pat.finditer(cleaned):
            literal = enclosing_string_literal(cleaned, match.start())
            if literal is not None and has_non_ascii(literal):
                hits.append(term)
                break
    return hits


def scan_file(path: Path) -> list[str]:
    rel = path.relative_to(REPO).as_posix()
    if any(frag in f"/{rel}/" for frag in SKIP_PATH_FRAGMENTS):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings: list[str] = []
    is_html = path.suffix == ".html"
    in_block_comment = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "/*" in line and "*/" not in line:
            in_block_comment = True
            continue
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
            continue
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if any(marker in line for marker in LINE_LEVEL_ALLOWED):
            continue
        hits = scan_html_line(line) if is_html else scan_js_or_css(line)
        for term in hits:
            snippet = line.strip()[:120]
            findings.append(f"{rel}:{lineno}: '{term}' 漏入 UI 文本 → `{snippet}`")
    return findings


def main() -> int:
    if not TARGET_DIR.exists():
        print(f"[skip] {TARGET_DIR} 不存在", file=sys.stderr)
        return 0
    findings: list[str] = []
    for path in sorted(TARGET_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in EXTENSIONS:
            continue
        findings.extend(scan_file(path))
    if findings:
        print("R12 工程术语漏入 UI（zw-brain-web/）：", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print(f"\n共 {len(findings)} 处违规", file=sys.stderr)
        return 1
    print("[OK] R12 UI 黑名单：zw-brain-web/ 全清", file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
