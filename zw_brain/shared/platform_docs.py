"""只读访问 zw-brain 仓库内文档，供平台问答 Agent / Skill 使用。"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MAX_READ_CHARS = 24_000
_DEFAULT_SEARCH_LIMIT = 8
_EXCERPT_CHARS = 500  # 增加 excerpt 长度，让 LLM 看到更多上下文，减少猜测文件名

# 排除策略（保留预检债务走内部，不暴露给平台指南）。
# 注意：approved/ / reconstructs/ 等目录包含经审批的正式文档（架构/角色/数据模型/
# 重构计划等），对用户有参考价值，不纳入排除列表。
_EXCLUDED_DOC_DIRS = ()
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
            if target.is_file():
                if not _is_excluded(target):
                    return target
                logger.info(
                    "平台指南文档被排除策略拦截 | rel_path=%s target=%s excluded_dirs=%s excluded_files=%s",
                    rel_path, target, _EXCLUDED_DOC_DIRS, _EXCLUDED_DOC_FILES,
                )
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
    """生成围绕查询关键词的上下文片段。

    优先包含文档标题（首个 # 行），让 LLM 能辨识文档身份和所在目录，
    减少因缺乏上下文而猜测文件名的倾向。
    """
    compact = re.sub(r"\s+", " ", text).strip()
    q = query.strip().lower()
    idx = compact.lower().find(q) if q else -1

    # 尝试在标题附近开始
    title_end = 0
    for line in text.splitlines()[:6]:
        if line.startswith("#"):
            title_end = len(line) + 1
            break

    if len(compact) <= _EXCERPT_CHARS:
        return compact

    if idx < 0:
        # 无匹配关键词时，从文档开头取
        return compact[:_EXCERPT_CHARS] + "…"

    # 以匹配位置为中心，但确保包含标题（若标题在 excerpt 范围内）
    half = _EXCERPT_CHARS // 2
    start = max(0, idx - half)
    # 如果标题信息可能在之前丢失，尝试从文档开头多包含一些
    if start > title_end and title_end <= half:
        start = 0

    end = min(len(compact), start + _EXCERPT_CHARS)
    snippet = compact[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(compact):
        snippet += "…"
    return snippet


def _fuzzy_suggest(bad_path: str, max_suggestions: int = 5) -> list[dict[str, object]]:
    """从 bad_path 中提取有意义的关键词，在文档库中搜索，返回最相关的 hits。

    用于 read_doc 在 FileNotFoundError 时提供 "你是不是要找……" 的友好提示，
    引导 LLM 使用正确的文件名而非继续猜测。
    """
    # 从路径中提取文件名部分（无后缀），并按非字母数字字符分割
    from pathlib import Path as _P
    stem = _P(bad_path).stem
    # 按连字符、下划线、空格、中文/非字母数字边界拆分
    tokens = re.findall(r"[\w一-鿿]+", stem)
    # 过滤掉太短或无意义的 token
    meaningful = [t for t in tokens if len(t) >= 2 and t.lower() not in ("md", "v1", "v2", "doc", "docs", "the", "and", "of", "for", "in")]
    if not meaningful:
        return []
    # 用前几个有意义的 token 构建搜索 query
    query = " ".join(meaningful[:4])
    try:
        result = search_docs(query=query, limit=max_suggestions)
        hits = result.get("hits", [])
        if isinstance(hits, list):
            return hits
    except Exception:
        pass
    return []


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


def _list_doc_dir(rel_path: str) -> dict[str, object]:
    """传入目录路径时，返回该目录下可读的文档概览。"""
    rel = rel_path.strip().rstrip("/")
    target = _resolve_dir(rel_path)
    if target is None:
        raise FileNotFoundError(f"directory not found: {rel_path}")

    # 找到 target 对应的 doc root
    base = None
    for root in doc_roots():
        if root.is_file():
            continue
        resolved = root.resolve()
        try:
            target.relative_to(resolved)
            base = resolved
            break
        except ValueError:
            continue

    if base is None:
        raise FileNotFoundError(f"directory not found: {rel_path}")

    parts: list[str] = []
    for md in sorted(target.rglob("*.md")):
        if not md.is_file():
            continue
        if _is_excluded(md):
            continue
        display = str(md.resolve().relative_to(base)).replace("\\", "/")
        parts.append(display)

    return {
        "path": rel,
        "is_directory": True,
        "entries": parts,
        "total": len(parts),
    }


def _resolve_dir(rel_path: str) -> Path | None:
    """尝试将 rel_path 解析为目录，返回第一个匹配的 Path，否则 None。"""
    rel = rel_path.strip().rstrip("/")
    for root in doc_roots():
        if root.is_file():
            continue
        base = root.resolve()
        for candidate in (rel, rel.removeprefix("docs/") if rel.startswith("docs/") else None):
            if candidate is None:
                continue
            target = (base / candidate).resolve()
            try:
                target.relative_to(base)
            except ValueError:
                continue
            if target.is_dir():
                return target
    return None


def read_doc(*, rel_path: str, max_chars: int | None = None) -> dict[str, object]:
    # 路径以 / 结尾 → 视为目录，返回目录下文档清单
    if rel_path.strip().endswith("/"):
        return _list_doc_dir(rel_path)

    try:
        path = _safe_resolve(rel_path)
    except FileNotFoundError:
        # 文档未找到时，自动搜索相似文档并提供提示
        suggestions = _fuzzy_suggest(rel_path, max_suggestions=5)
        result: dict[str, object] = {
            "error": "document_not_found",
            "path": rel_path,
            "message": (
                f"文档不存在：{rel_path}。请使用 search_docs 搜索相关关键词找到正确的文档路径，"
                f"然后再用正确的路径调用 read_doc。不要猜测或编造文件名。"
            ),
            "suggestion": f"请对 '{rel_path}' 相关的关键词执行 search_docs 以找到正确的文档路径",
        }
        if suggestions:
            result["did_you_mean"] = [s["path"] for s in suggestions]
        # 记录日志以便排查
        logger.info(
            "平台指南 read_doc 文件不存在，建议改用 search_docs | rel_path=%s did_you_mean=%s",
            rel_path,
            result.get("did_you_mean"),
        )
        return result

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
