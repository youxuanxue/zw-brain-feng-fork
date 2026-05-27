"""Tests for scripts/check_approved_doc_drift.py (preflight 段 44 — D-编号回灌守卫).

覆盖 R-001 silent-swallow 修复 + 状态机边界场景：
- 不可解析 base ref 必须 FAIL（exit 1）而非伪绿
- 本地 main / HEAD == base 时 skip（exit 0）
- D-编号提取兼容 D32 / D32.a / D32.d 子项
- 反引号路径白名单（docs/ / .testing/ / tests/fixtures/）正确过滤
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_approved_doc_drift.py"


def _run(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """跑脚本，返回 CompletedProcess（合并 stdout/stderr）。"""
    import os

    env = os.environ.copy()
    # 清掉父进程可能携带的 PR-mode env，避免污染单测
    env.pop("PREFLIGHT_BASE", None)
    env.pop("ZW_BRAIN_DRIFT_BASE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# ── R-001 修复：base 不可解析必须 FAIL（exit 1）而非伪绿 ─────────────────


def test_unresolvable_base_via_arg_fails_explicitly() -> None:
    """`--base nonexistent-ref` 应明确 FAIL 而非 silently OK。

    R-001 修复前：args.base 短路 _resolve_base，git diff 失败 → 空串 → 报"无 diff" 伪绿。
    R-001 修复后：所有 base path 都过 _validate_base，不可解析时 print FAIL + exit 1。
    """
    result = _run("--base", "nonexistent-ref-12345")
    assert result.returncode == 1, f"应 exit 1，实际 {result.returncode}\n{result.stdout}"
    assert "FAIL" in result.stdout
    assert "不可解析" in result.stdout


def test_unresolvable_base_via_env_fails_explicitly() -> None:
    """`PREFLIGHT_BASE=nonexistent` 也应明确 FAIL。"""
    result = _run(env_extra={"PREFLIGHT_BASE": "nonexistent-ref-12345"})
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "不可解析" in result.stdout


# ── skip 路径（合理 0 退出） ────────────────────────────────────────────


def test_no_env_no_arg_skips() -> None:
    """没有 PREFLIGHT_BASE 且没传 --base 时 skip（本地非 PR-mode）。"""
    result = _run()
    assert result.returncode == 0
    assert "skip" in result.stdout
    assert "非 PR-mode" in result.stdout


def test_head_equals_base_skips() -> None:
    """HEAD == base 时 skip（合理：本分支无新增 commit）。"""
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT
    ).decode().strip()
    result = _run("--base", head)
    assert result.returncode == 0
    assert "skip" in result.stdout
    assert "HEAD ==" in result.stdout


# ── 状态机：D-编号识别 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "line,expected",
    [
        ("- [2026-05-27] D32：内容", "D32"),
        ("- [2026-05-27] D32.a：内容", "D32.a"),
        ("- [2026-05-27] D32.d：内容", "D32.d"),
        ("* [2026-05-27] D33：星号 bullet 也合法", "D33"),
        ("- [2026-05-27] D32:含半角冒号", "D32"),
        # 负向：不是 D-编号
        ("- [2026-05-27] 普通条目：不算", None),
        ("### [2026-05-27] D34 retrofit：标题不是段头", None),
        ("非 bullet 起始 D32", None),
    ],
)
def test_d_number_header_regex(line: str, expected: str | None) -> None:
    """D-编号段头正则覆盖 D32 / D32.a / 半角/全角冒号 / 星号 bullet 等。"""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("cadd", SCRIPT)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        m = mod.D_NUM_HEADER_RE.match(line.lstrip())
        if expected is None:
            assert m is None, f"line={line!r} 应不匹配但匹配到 {m.group(1) if m else None}"
        else:
            assert m is not None and m.group(1) == expected
    finally:
        sys.path.pop(0)


# ── 反引号路径白名单（R-005 修复） ────────────────────────────────────


def test_path_prefix_whitelist_accepts_three_roots(tmp_path: Path) -> None:
    """`docs/...` / `.testing/...` / `tests/fixtures/...` 都应通过白名单。

    R-005 修复前：仅 docs/ 前缀过滤；与 SCAN_ROOTS 声明（含 .testing/）不一致。
    R-005 修复后：白名单与 SCAN_ROOTS 对齐。
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("cadd", SCRIPT)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        block = [
            "- [2026-05-27] D99：refer to `docs/foo.md` and `.testing/bar.md` "
            "and `tests/fixtures/baz.md` and `../outside.md`",
        ]
        paths, _, _ = mod._extract_keywords(block)
        assert "docs/foo.md" in paths
        assert ".testing/bar.md" in paths
        assert "tests/fixtures/baz.md" in paths
        assert "../outside.md" not in paths
    finally:
        sys.path.pop(0)


# ── 核心漂移判定行为（_find_drift_candidates） ────────────────────────


def _load_mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location("cadd", SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_find_drift_candidates_flags_high_density_without_d_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件高密度（≥阈值）提到 path 但未引用 D-编号 → 漂移候选；
    自引用文件（path 自身）与引用了 D-编号的文件不报。"""
    mod = _load_mod()
    target = "docs/foo-plan.md"
    drifting = tmp_path / "docs" / "other.md"
    drifting.parent.mkdir(parents=True)
    # 高密度提及 target 但从不提 D99
    drifting.write_text("\n".join([f"see `{target}`"] * 4), encoding="utf-8")
    referenced = tmp_path / "docs" / "synced.md"
    # 同样高密度，但回引了 D99 → 不应报
    referenced.write_text(
        "\n".join([f"see `{target}` per D99"] * 4), encoding="utf-8"
    )
    selfref = tmp_path / target  # path 自身 → 自引用排除
    selfref.write_text("\n".join([f"`{target}`"] * 4), encoding="utf-8")
    low = tmp_path / "docs" / "rare.md"
    # 仅 1 次提及 < 阈值 → 不应报
    low.write_text(f"see `{target}` once", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "SCAN_ROOTS", [tmp_path / "docs"])
    monkeypatch.setattr(mod, "SCAN_FILES", [])

    findings = mod._find_drift_candidates("D99", {target}, set())
    # 被 flag 的文件出现在 "→ <rel>:" 位置
    flagged = {f.split("→", 1)[1].split(":", 1)[0].strip() for f in findings}
    assert flagged == {"docs/other.md"}, f"got {flagged}"
