"""平台文档只读 Skill 与路径安全。"""
from __future__ import annotations

import pytest

from zw_brain.shared import platform_docs

pytestmark = pytest.mark.no_db


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


def test_default_doc_roots_exclude_preflight_debt_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-005 — 默认根下 docs/preflight-debt.md 不可经平台指南检索/读取。

    docs/approved/ 和 docs/reconstructs/ 现已解禁（经审批的架构/角色/数据模型/
    重构计划对用户有参考价值），只排除 preflight-debt.md 内部债务产物。
    """
    monkeypatch.delenv("ZW_BRAIN_PLATFORM_DOCS_ROOTS", raising=False)
    files = platform_docs._iter_markdown_files()
    # approved/ 和 reconstructs/ 不再视为内部产物排除
    leaked_preflight = [f for f in files if f.name == "preflight-debt.md"]
    assert leaked_preflight == [], f"preflight-debt.md leaked via default doc_roots: {leaked_preflight}"
    # approved/ 和 reconstructs/ 应可检索
    approved = [f for f in files if "/docs/approved/" in str(f)]
    reconstructs = [f for f in files if "/docs/reconstructs/" in str(f)]
    assert len(approved) > 0, "approved/ should be searchable (unblocked)"
    assert len(reconstructs) > 0, "reconstructs/ should be searchable (unblocked)"
    # preflight-debt.md 仍不可用
    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("preflight-debt.md")
    # approved 和 reconstructs 中的文档应可读取
    approved_doc = platform_docs._safe_resolve("approved/zw-brain-architecture.md")
    assert approved_doc.exists()
    reconstructs_doc = platform_docs._safe_resolve("reconstructs/dsp-exchange-reconstruction-plan-v1.md")
    assert reconstructs_doc.exists()


def test_explicit_doc_roots_still_exclude_preflight_only(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-001 — ZW_BRAIN_PLATFORM_DOCS_ROOTS 显式设置（Docker 生产 /app/docs）时只排除 preflight-debt.md。

    覆盖 wheel-install 场景：_REPO_ROOT 指向 site-packages，与 docs 根不在同一前缀；
    _is_excluded 需对每个 doc_roots() 分别 relative_to 才不被 ValueError 静默吞掉。
    """
    docs = tmp_path / "docs"
    (docs / "approved").mkdir(parents=True)
    (docs / "reconstructs").mkdir()
    (docs / "approved" / "public.md").write_text("# Approved public doc\n业务决策\n", encoding="utf-8")
    (docs / "reconstructs" / "plan.md").write_text("# Reconstruct plan\n重构\n", encoding="utf-8")
    (docs / "preflight-debt.md").write_text("# Debt\n技术债\n", encoding="utf-8")
    (docs / "misc.md").write_text("# Misc\n用户面向\n", encoding="utf-8")
    monkeypatch.setenv("ZW_BRAIN_PLATFORM_DOCS_ROOTS", str(docs))

    files = platform_docs._iter_markdown_files()
    names = {f.name for f in files}
    assert "misc.md" in names
    assert "public.md" in names  # approved/ 已解禁
    assert "plan.md" in names  # reconstructs/ 已解禁
    assert "preflight-debt.md" not in names

    # approved/ 和 reconstructs/ 中的文档现在可读取
    approved_body = platform_docs.read_doc(rel_path="approved/public.md")
    assert "Approved public doc" in approved_body["content"]
    reconstructs_body = platform_docs.read_doc(rel_path="reconstructs/plan.md")
    assert "Reconstruct plan" in reconstructs_body["content"]
    # preflight-debt.md 仍被排除
    with pytest.raises(FileNotFoundError):
        platform_docs._safe_resolve("preflight-debt.md")


def test_platform_guide_user_whitepaper_is_searchable_and_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    """平台指南默认文档库必须能命中新客户流程白皮书。"""
    monkeypatch.delenv("ZW_BRAIN_PLATFORM_DOCS_ROOTS", raising=False)

    result = platform_docs.search_docs(query="新客户第一次怎么使用平台", limit=5)
    paths = [hit["path"] for hit in result["hits"]]
    assert "user-whitepaper-platform-guide.md" in paths

    body = platform_docs.read_doc(rel_path="user-whitepaper-platform-guide.md")
    content = str(body["content"])
    assert "按业务流程理解平台" in content
    assert "各角色在流程中的位置和操作" in content
    assert "申请共享数据从找数到交付怎么走" in content
