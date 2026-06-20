#!/usr/bin/env python3
"""check_no_placeholder_word.py — webui 占位套话源码级兜底守卫

禁词「功能建设中」等占位套话不得出现在前端源码（zw-brain-web/src/**）的 .vue / .ts 里。

为什么需要这道守卫（与既有守卫的区别）：
    scripts/jobs_page_audit.py / scripts/customer_acceptance_checklist.py /
    tests/e2e/twin_browser_pages.spec.ts 都是**固定 PAGE 白名单**驱动 —— 只能验白名单
    里枚举过的页面，漏掉「只能手敲 URL 到达的死路由」（如曾经的 /profile）。
    本守卫不依赖任何路由 / 页面白名单，而是直接 grep 整个 src 树的源码，
    占位套话一旦写进任何 .vue/.ts 就拦截，是 URL-only 路由也覆盖得到的源码级兜底。

判定模型（刻意简单、确定性）：
    禁词本身全是非 ASCII 中文 / 明确的英文占位语，不是 capability slug / 路由 /
    标识符，不存在「合法 ASCII 标识符误伤」问题，故直接做**原始行子串匹配**，
    不做字符串字面值剥离 —— 出现即违规。

退出码：0 = 全部通过；非零 = 至少一处命中（打印 文件:行）。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO / "zw-brain-web" / "src"

# 占位套话黑名单（task T1 列举 + 同类常见占位语）。大小写不敏感匹配英文项。
# 「功能建设中」是头号目标（twin_browser_pages 断言 count=0 的那条）。
PLACEHOLDER_WORDS = (
    "功能建设中",
    "建设中",
    "敬请期待",
    "即将上线",
    "敬请关注",
    "coming soon",
    "under construction",
)

EXTENSIONS = (".vue", ".ts")

SKIP_PATH_FRAGMENTS = (
    "/node_modules/",
    "/__pycache__/",
    "/.git/",
    "/dist/",
    "/dist-vite/",
    "/build/",
)

# 行级豁免：仅守卫自身的文档串 / 显式标注。本守卫源码不在 TARGET_DIR 下，
# 一般无需豁免；保留口子与其它守卫风格一致。
LINE_LEVEL_ALLOWED = ("placeholder-word-exempt",)


def scan_file(path: Path) -> list[str]:
    rel = path.relative_to(REPO).as_posix()
    if any(frag in f"/{rel}/" for frag in SKIP_PATH_FRAGMENTS):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    findings: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if any(marker in line for marker in LINE_LEVEL_ALLOWED):
            continue
        lower = line.lower()
        for word in PLACEHOLDER_WORDS:
            needle = word if word.isascii() is False else word.lower()
            haystack = line if word.isascii() is False else lower
            if needle in haystack:
                snippet = line.strip()[:120]
                findings.append(f"{rel}:{lineno}: 占位套话 '{word}' → `{snippet}`")
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
        print("占位套话漏入 webui 源码（zw-brain-web/src/**）：", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print(f"\n共 {len(findings)} 处违规", file=sys.stderr)
        return 1
    print("ok: webui 源码无占位套话（zw-brain-web/src/**，.vue/.ts）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
