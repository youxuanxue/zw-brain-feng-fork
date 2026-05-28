"""平台文档只读 Skill 与路径安全。"""
from __future__ import annotations

import pytest

from zw_brain.shared import platform_docs


@pytest.fixture
def docs_root(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "alpha.md").write_text("# Alpha\n\nDocker 端口 8800。\n", encoding="utf-8")
    (docs / "nested").mkdir()
    (docs / "nested" / "beta.md").write_text("# Beta\n\n租户 sd-default。\n", encoding="utf-8")
    monkeypatch.setenv("ZW_BRAIN_PLATFORM_DOCS_ROOTS", str(docs))


def test_search_docs_finds_keyword(docs_root: None) -> None:
    result = platform_docs.search_docs(query="Docker")
    assert result["total"] >= 1
    paths = {hit["path"] for hit in result["hits"]}
    assert "alpha.md" in paths


def test_read_doc_returns_content(docs_root: None) -> None:
    body = platform_docs.read_doc(rel_path="nested/beta.md")
    assert "sd-default" in body["content"]
    assert body["path"] == "nested/beta.md"


def test_read_doc_rejects_traversal(docs_root: None) -> None:
    with pytest.raises(ValueError, match="traversal"):
        platform_docs.read_doc(rel_path="../secret.md")


def test_default_doc_roots_exclude_internal_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-005 — 默认根下 docs/approved/、docs/reconstructs/、docs/preflight-debt.md 不可经平台指南检索/读取。"""
    monkeypatch.delenv("ZW_BRAIN_PLATFORM_DOCS_ROOTS", raising=False)
    files = platform_docs._iter_markdown_files()
    leaked = [f for f in files if "/docs/approved/" in str(f) or "/docs/reconstructs/" in str(f) or f.name == "preflight-debt.md"]
    assert leaked == [], f"internal docs leaked via default doc_roots: {leaked}"
    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("approved/zw-brain-architecture.md")
    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("preflight-debt.md")


def test_explicit_doc_roots_still_exclude_internal_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-001 — ZW_BRAIN_PLATFORM_DOCS_ROOTS 显式设置（Docker 生产 /app/docs）时仍排除内部产物。

    覆盖 wheel-install 场景：_REPO_ROOT 指向 site-packages，与 docs 根不在同一前缀；
    _is_excluded 需对每个 doc_roots() 分别 relative_to 才不被 ValueError 静默吞掉。
    """
    docs = tmp_path / "docs"
    (docs / "approved").mkdir(parents=True)
    (docs / "reconstructs").mkdir()
    (docs / "approved" / "secret.md").write_text("# Secret\n业务决策\n", encoding="utf-8")
    (docs / "reconstructs" / "plan.md").write_text("# Plan\n重构\n", encoding="utf-8")
    (docs / "preflight-debt.md").write_text("# Debt\n技术债\n", encoding="utf-8")
    (docs / "public.md").write_text("# Public\n用户面向\n", encoding="utf-8")
    monkeypatch.setenv("ZW_BRAIN_PLATFORM_DOCS_ROOTS", str(docs))

    files = platform_docs._iter_markdown_files()
    names = {f.name for f in files}
    assert "public.md" in names
    assert "secret.md" not in names
    assert "plan.md" not in names
    assert "preflight-debt.md" not in names

    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("approved/secret.md")
    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("reconstructs/plan.md")
    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("preflight-debt.md")
