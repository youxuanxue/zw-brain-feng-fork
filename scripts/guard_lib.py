#!/usr/bin/env python3
"""guard_lib.py — 守卫脚本通用基座（R-019⑤/R-020 库化提速）.

零散 grep 类 preflight 守卫此前各自重复：定位 repo root、``rglob`` 全树遍历、
逐行扫描 + 豁免判定。库化收口三件事：

1. **单趟文件枚举**：``tracked_text_files()`` 用一次 ``git ls-files`` 取全部受跟踪
   文件（替代每个守卫各跑一遍 ``rglob``——既避开 .gitignore 噪声又只付一次
   遍历成本）。回落 ``rglob``（非 git 树 / shallow checkout）。
2. **SKIP_PATH_FRAGMENTS 单一事实源**：守卫共享同一套跳过片段，避免各自手抄漂移。
3. **逐行扫描器 + 行级豁免**：``scan_lines`` 统一「读文件→逐行匹配→行级豁免」语义；
   行级豁免注释 ``# guard-exempt: <理由>`` **冒号后必须有非空理由文本**（无理由的
   裸豁免不生效，防「一注释了之」）。

外加**守卫面注册表**（``register_grep_guard``）：每个 grep 类守卫声明自己的
``(roots, extensions)`` 扫描面，供元守卫 ``check_guard_scan_surface.py`` 对账
「声明面 vs 实际文件类型分布」，防守卫面随代码演进漂移（R12 只扫 .html/.js/.css
漏 .vue 是头号缺陷实证）。

合并遍历器 ``scan_many`` 让多个同构守卫共享一次文件遍历（段 19/20/21 合并）。
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def repo_root() -> Path:
    return REPO_ROOT


# ── 共享跳过片段（单一事实源）─────────────────────────────────────────────
# 以 REPO 相对路径 "/<rel>" 形式做子串匹配（与既有守卫 should_skip_path 同语义）。
# worktree 副本场景：必须用相对路径匹配，绝对路径会把整仓误跳过（本地假绿/CI 红）。
SKIP_PATH_FRAGMENTS: tuple[str, ...] = (
    "/.venv/",
    "/.venv-py312/",
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/.claude/worktrees/",
    "/.claude/twin-workspaces/",
    "/.data/",
    "/.reviews/",
    "/.experiences/",
    "/old/",
    "/.legacy_cache/",
    "/dist/",
    "/dist-vite/",
    "/build/",
)


def is_skipped(rel_posix: str, skip_fragments: Sequence[str] = SKIP_PATH_FRAGMENTS) -> bool:
    """rel_posix = REPO 相对 posix 路径（无前导斜杠）。"""
    needle = f"/{rel_posix}"
    return any(frag in needle for frag in skip_fragments)


def tracked_text_files() -> list[Path]:
    """全部受 git 跟踪的文件（单趟 ``git ls-files``）。

    非 git 树 / git 不可用 → 回落 ``rglob('*')``。返回绝对 Path。
    调用方再按扩展名 / skip-fragment / roots 过滤——本函数不做内容判定。
    """
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=30,
        )
        rels = [r for r in out.stdout.decode("utf-8", "ignore").split("\0") if r]
        return [REPO_ROOT / r for r in rels]
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return [p for p in REPO_ROOT.rglob("*") if p.is_file()]


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(
    *,
    extensions: Sequence[str],
    roots: Sequence[str] | None = None,
    skip_fragments: Sequence[str] = SKIP_PATH_FRAGMENTS,
    allowed_files: Iterable[str] = (),
) -> Iterator[Path]:
    """枚举受跟踪文件，按扩展名 / skip-fragment / roots / allowed-file 过滤。

    - ``extensions``：含点扩展名元组（如 ``(".py", ".vue")``）；空=不限扩展名。
    - ``roots``：REPO 相对目录前缀（如 ``("zw_brain", "scripts")``）；None=全仓。
    - ``allowed_files``：整文件豁免（REPO 相对 posix），命中则不产出。
    """
    exts = set(extensions)
    allow = set(allowed_files)
    norm_roots = tuple(r.rstrip("/") for r in roots) if roots else None
    for path in tracked_text_files():
        if not path.is_file():
            continue
        if exts and path.suffix not in exts:
            continue
        rel = _rel(path)
        if is_skipped(rel, skip_fragments):
            continue
        if rel in allow:
            continue
        if norm_roots is not None and not any(
            rel == r or rel.startswith(f"{r}/") for r in norm_roots
        ):
            continue
        yield path


# ── 行级豁免：``# guard-exempt: <理由>``（冒号后须有非空理由文本）──────────
def line_has_reasoned_exempt(line: str, marker: str = "# guard-exempt:") -> bool:
    """行内带 ``marker`` 且冒号后有非空理由文本 → True（豁免生效）。

    裸 ``# guard-exempt:``（冒号后空白）不豁免——防「一注释了之」绕过。
    支持守卫自定义 marker（如 ``# adapter-write-ok:``）。
    """
    idx = line.find(marker)
    if idx == -1:
        return False
    reason = line[idx + len(marker):].strip()
    return bool(reason)


@dataclass
class Violation:
    path: str  # REPO 相对 posix
    lineno: int
    line: str
    reason: str = ""

    def render(self, max_len: int = 160) -> str:
        tag = f" [{self.reason}]" if self.reason else ""
        return f"{self.path}:{self.lineno}:{tag} {self.line.strip()[:max_len]}"


# 行匹配器：(line) → (matched: bool, reason: str)
LineMatcher = Callable[[str], "tuple[bool, str]"]


def scan_lines(
    path: Path,
    matcher: LineMatcher,
    *,
    allowed_line_markers: Sequence[str] = (),
    exempt_marker: str | None = None,
) -> list[Violation]:
    """逐行扫描单文件，产出 Violation 列表。

    - ``matcher(line)`` → ``(True, reason)`` 表示命中。
    - ``allowed_line_markers``：同行命中任一短语即跳过该行（守卫特定语义豁免）。
    - ``exempt_marker``：行级带理由豁免注释（默认不启用；传入则用
      ``line_has_reasoned_exempt`` 判定）。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (UnicodeDecodeError, OSError):
        return []
    rel = _rel(path)
    out: list[Violation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if allowed_line_markers and any(m in line for m in allowed_line_markers):
            continue
        if exempt_marker and line_has_reasoned_exempt(line, exempt_marker):
            continue
        matched, reason = matcher(line)
        if matched:
            out.append(Violation(rel, lineno, line, reason))
    return out


@dataclass
class GuardSpec:
    """单个 grep 类守卫的扫描面声明 + 行匹配逻辑（供合并遍历 + 元守卫对账）。"""
    section_id: str               # 报错前缀 / 段标识（如 "no-legacy-role-codes"）
    extensions: tuple[str, ...]
    matcher: LineMatcher
    roots: tuple[str, ...] | None = None
    allowed_files: tuple[str, ...] = ()
    allowed_line_markers: tuple[str, ...] = ()
    exempt_marker: str | None = None
    skip_fragments: tuple[str, ...] = SKIP_PATH_FRAGMENTS


def scan_many(specs: Sequence[GuardSpec]) -> dict[str, list[Violation]]:
    """多守卫共享一次文件遍历：合并 specs 的扩展名并集做单趟枚举，
    每个文件按各 spec 的扩展名 / roots / allowed-file 归属判定后逐行扫一次。

    返回 ``{section_id: [Violation, ...]}``；每个 spec 还回填 ``files_scanned``
    到结果对象外的 ``scan_many.scanned`` 字典（供报错统计）。
    """
    union_exts = set()
    for s in specs:
        union_exts |= set(s.extensions)
    results: dict[str, list[Violation]] = {s.section_id: [] for s in specs}
    scanned: dict[str, int] = {s.section_id: 0 for s in specs}

    for path in iter_files(extensions=tuple(union_exts)):
        rel = _rel(path)
        for s in specs:
            if path.suffix not in s.extensions:
                continue
            if s.roots is not None and not any(
                rel == r.rstrip("/") or rel.startswith(f"{r.rstrip('/')}/") for r in s.roots
            ):
                continue
            if rel in s.allowed_files:
                continue
            if is_skipped(rel, s.skip_fragments):
                continue
            scanned[s.section_id] += 1
            results[s.section_id].extend(
                scan_lines(
                    path,
                    s.matcher,
                    allowed_line_markers=s.allowed_line_markers,
                    exempt_marker=s.exempt_marker,
                )
            )
    scan_many.scanned = scanned  # type: ignore[attr-defined]
    return results


# ── 守卫面注册表（元守卫 check_guard_scan_surface 消费）────────────────────
@dataclass
class GuardSurface:
    """一个 grep 类守卫声明的扫描面（roots + extensions），供元守卫对账。"""
    name: str
    roots: tuple[str, ...]          # REPO 相对目录前缀；() = 全仓
    extensions: tuple[str, ...]
    note: str = ""


_GUARD_SURFACES: dict[str, GuardSurface] = {}


def register_grep_guard(
    name: str,
    *,
    roots: Sequence[str],
    extensions: Sequence[str],
    note: str = "",
) -> GuardSurface:
    """守卫在 import 时声明自己的扫描面；元守卫据此对账实际文件分布。"""
    surface = GuardSurface(name, tuple(roots), tuple(extensions), note)
    _GUARD_SURFACES[name] = surface
    return surface


def registered_surfaces() -> dict[str, GuardSurface]:
    return dict(_GUARD_SURFACES)
