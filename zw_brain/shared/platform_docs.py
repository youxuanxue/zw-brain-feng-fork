"""只读访问 zw-brain 仓库内文档，供平台问答 Agent / Skill 使用。"""

from __future__ import annotations

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MAX_READ_CHARS = 24_000
_DEFAULT_SEARCH_LIMIT = 8
_EXCERPT_CHARS = 320

# 内部研发产物，禁止经面向最终用户的「平台指南」Agent 暴露（决策记录 / 审批基线 /
# 重构计划 / 技术债）。默认 docs 根下命中这些前缀的文件一律排除。
_EXCLUDED_DOC_DIRS = ("approved", "reconstructs")
_EXCLUDED_DOC_FILES = ("preflight-debt.md",)


def doc_roots() -> list[Path]:
    """可搜索文档根：目录递归 *.md；单文件根仅匹配 basename。"""
    raw = (os.environ.get("ZW_BRAIN_PLATFORM_DOCS_ROOTS") or "").strip()
    if raw:
        roots = [Path(part.strip()) for part in raw.split(os.pathsep) if part.strip()]
    else:
        # 默认仅暴露面向用户的 docs/ 树；CLAUDE.md / AGENTS.md（研发宪法）不进可检索范围。
        roots = [_REPO_ROOT / "docs"]
    return [root for root in roots if root.exists()]


def _is_excluded(resolved: Path) -> bool:
    """命中内部产物排除规则。

    对每个配置 doc 根分别计算 relative_to，使默认根（_REPO_ROOT/docs）与显式
    ZW_BRAIN_PLATFORM_DOCS_ROOTS（Docker 生产默认 /app/docs，与 wheel-install
    _REPO_ROOT 不在同一前缀）两条路径都能生效。单文件根跳过 — 单文件由部署侧
    显式声明，不参与目录级内部产物排除。
    """
    for root in doc_roots():
        if root.is_file():
            continue
        try:
            rel = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in _EXCLUDED_DOC_DIRS:
            return True
        if rel.name in _EXCLUDED_DOC_FILES:
            return True
    return False


def _iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root in doc_roots():
        if root.is_file():
            resolved = root.resolve()
            if resolved.suffix.lower() == ".md" and resolved not in seen and not _is_excluded(resolved):
                seen.add(resolved)
                files.append(resolved)
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                continue
            if resolved in seen or _is_excluded(resolved):
                continue
            seen.add(resolved)
            files.append(resolved)
    return files


def _display_path(path: Path) -> str:
    for root in doc_roots():
        if root.is_file():
            if path.resolve() == root.resolve():
                return root.name
            continue
        try:
            return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            continue
    return str(path)


def _safe_resolve(rel_path: str) -> Path:
    rel = rel_path.strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("rel_path is required")
    parts = Path(rel).parts
    if ".." in parts:
        raise ValueError("path traversal denied")

    candidates: list[str] = [rel]
    if rel.startswith("docs/"):
        candidates.append(rel.removeprefix("docs/"))

    for root in doc_roots():
        if root.is_file():
            for candidate in candidates:
                if candidate == root.name:
                    return root.resolve()
            continue
        base = root.resolve()
        for candidate in candidates:
            target = (base / candidate).resolve()
            try:
                target.relative_to(base)
            except ValueError:
                continue
            if target.is_file() and not _is_excluded(target):
                return target
    raise FileNotFoundError(f"document not found: {rel_path}")


def _score_content(text: str, query: str) -> int:
    lowered = text.lower()
    q = query.strip().lower()
    if not q:
        return 0
    score = lowered.count(q) * 3
    for token in re.findall(r"[\w\u4e00-\u9fff]+", q):
        if len(token) < 2:
            continue
        score += lowered.count(token)
    return score


def _excerpt(text: str, query: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= _EXCERPT_CHARS:
        return compact
    q = query.strip().lower()
    idx = compact.lower().find(q) if q else -1
    if idx < 0:
        return compact[:_EXCERPT_CHARS] + "…"
    start = max(0, idx - 80)
    end = min(len(compact), idx + _EXCERPT_CHARS - 80)
    snippet = compact[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(compact):
        snippet += "…"
    return snippet


def search_docs(*, query: str, limit: int | None = None) -> dict[str, object]:
    q = query.strip()
    if not q:
        raise ValueError("query is required")
    cap = limit if limit is not None else _DEFAULT_SEARCH_LIMIT
    cap = max(1, min(int(cap), 20))

    hits: list[dict[str, object]] = []
    for path in _iter_markdown_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        score = _score_content(text, q)
        if score <= 0:
            continue
        title = ""
        for line in text.splitlines()[:12]:
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
        hits.append(
            {
                "path": _display_path(path),
                "title": title or path.name,
                "score": score,
                "excerpt": _excerpt(text, q),
            }
        )
    hits.sort(key=lambda item: int(item["score"]), reverse=True)
    return {"query": q, "hits": hits[:cap], "total": len(hits)}


def read_doc(*, rel_path: str, max_chars: int | None = None) -> dict[str, object]:
    path = _safe_resolve(rel_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    limit = max_chars if max_chars is not None else _DEFAULT_MAX_READ_CHARS
    limit = max(500, min(int(limit), _DEFAULT_MAX_READ_CHARS))
    truncated = len(text) > limit
    content = text[:limit] if truncated else text
    return {
        "path": _display_path(path),
        "content": content,
        "truncated": truncated,
        "size_chars": len(text),
    }
