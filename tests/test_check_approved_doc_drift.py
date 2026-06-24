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

pytestmark = pytest.mark.no_db

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
        # 真实索引格式 = D 号在前（D64 起索引在 docs/decisions/decision-log.md）：
        # 早期无日期括注 / Retrofit 起带 [MM-DD] / 后期带 **scope** 加粗，冒号半/全角皆可。
        ("- D1：产品形态 = 精简 WebUI", "D1"),
        ("- D29：R 编号空间区分", "D29"),
        ("- D30 [05-24]：AgentRuntime 触发式落地", "D30"),
        ("- D32.a [05-27]：子编号也合法", "D32.a"),
        ("- D32.d [05-27]：子编号也合法", "D32.d"),
        ("* D33 [05-28]：星号 bullet 也合法", "D33"),
        ("- D32 [05-27]:含半角冒号", "D32"),
        ("- D46 [05-30] **feature-status-as-function**（架构门）：带 scope 加粗", "D46"),
        # 负向：不是 D-编号段头
        ("- [06-13] **可机械化边界**：方法论 bullet（日期在前、无 D 号）", None),
        ("- [2026-05-27] 普通条目：不算", None),
        ("### GATE-1 设计基线（2026-04-18，D1–D22）：章节标题含 D 号但不是段头", None),
        ("非 bullet 起始 D32", None),
    ],
)
def test_d_number_header_regex(line: str, expected: str | None) -> None:
    """D-编号段头正则覆盖真实「D 号在前」格式：无日期 / 带 [MM-DD] / 带 **scope**、
    子编号 D32.a、半/全角冒号、星号 bullet；拒方法论 bullet（日期在前无 D 号）与章节标题。"""
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
        paths, _, _, _ = mod._extract_keywords(block)
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

    findings = mod._find_drift_candidates("D99", {target}, set(), set())
    # 被 flag 的文件出现在 "→ <rel>:" 位置
    flagged = {f.split("→", 1)[1].split(":", 1)[0].strip() for f in findings}
    assert flagged == {"docs/other.md"}, f"got {flagged}"


# ── Namespace 漂移启发式（PR #140 D32.d 启发式盲区修复） ─────────────────


def test_namespace_extraction_from_d32_block() -> None:
    """D32 段内反引号 namespace 形态全提取（pattern 边界 test）。

    样本来自 CLAUDE.md D32 实际段，覆盖 4 种典型形态：
      - `resource.api.{register,change,...}` → root "resource.api"
      - `ops.gateway.{heartbeat.ingest,log.anchor}` → root "ops.gateway"
      - `ops.service.{report.query,invocation.query}` → root "ops.service"
      - `topic.package.*` → root "topic.package"
    """
    mod = _load_mod()
    block = [
        "- [2026-05-27] D99：A 类 → 按 plan §3.5 12 capability "
        "(`resource.api.{register,change,submit_review,review,publish,withdraw,"
        "revoke,test,policy.update}` + `ops.gateway.{heartbeat.ingest,log.anchor}` + "
        "`ops.service.{report.query,invocation.query}`)；D 类 → "
        "`topic.package.*` 系列；H 类按 §H.1 不复活。"
    ]
    _, _, _, namespaces = mod._extract_keywords(block)
    # 仅提取 root 两段（避免子能力组合爆炸）
    assert namespaces == {
        "resource.api",
        "ops.gateway",
        "ops.service",
        "topic.package",
    }, f"got {namespaces}"


def test_namespace_missing_from_approved_flags_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """namespace 在 docs/approved/*.md 完全 0 次出现 → 漂移候选。

    PR #140 启发式盲区原本场景：D32 引入 ops.service.*，架构基线 §6.6 未列；
    段 44 原版扫不到，加 namespace 启发式后能抓到。
    """
    mod = _load_mod()
    arch = tmp_path / "docs" / "approved" / "zw-brain-architecture.md"
    arch.parent.mkdir(parents=True)
    # 架构基线只列了 ops.gateway，没有 ops.service / topic.package
    arch.write_text("§6.6 命名空间预算：`ops.gateway.*`、`ops.shift_handover.*`")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(
        mod,
        "APPROVED_DOCS",
        ["docs/approved/zw-brain-architecture.md"],
    )
    findings = mod._find_drift_candidates(
        "D99",
        set(),
        set(),
        {"ops.gateway", "ops.service", "topic.package"},
    )
    # ops.gateway 在 doc 中出现过 → 不报；ops.service / topic.package 全 0 → 报
    flagged_ns = {
        f.split("namespace `", 1)[1].split(".*", 1)[0]
        for f in findings
        if "namespace `" in f
    }
    assert flagged_ns == {"ops.service", "topic.package"}, f"got {flagged_ns}"


def test_namespace_present_in_any_approved_doc_is_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """namespace 在任一 approved doc 出现 ≥1 次 → 不报（即使其他 doc 没提）。

    这避免误报：approved doc 是多文件构成的 set，命名空间在 §6.6 一处提即可。
    """
    mod = _load_mod()
    arch = tmp_path / "docs" / "approved" / "zw-brain-architecture.md"
    fly = tmp_path / "docs" / "approved" / "zw-brain-flywheel.md"
    arch.parent.mkdir(parents=True)
    arch.write_text("§6.6 命名空间预算：`ops.service.*`")  # 唯一提到 ops.service 的地方
    fly.write_text("飞轮 §四 没提 ops.service")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(
        mod,
        "APPROVED_DOCS",
        [
            "docs/approved/zw-brain-architecture.md",
            "docs/approved/zw-brain-flywheel.md",
        ],
    )
    findings = mod._find_drift_candidates(
        "D99", set(), set(), {"ops.service"}
    )
    assert findings == [], f"unexpected findings: {findings}"


def test_namespace_drift_independent_of_path_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """namespace 漂移与 path 漂移独立累加（同一 D-编号可两类同时报）。"""
    mod = _load_mod()
    # 接路径漂移侧：高密度 path 引用 + 未引用 D99
    target = "docs/foo-plan.md"
    drifting = tmp_path / "docs" / "approved" / "zw-brain-architecture.md"
    drifting.parent.mkdir(parents=True)
    # arch 同时：高密度 path 引用未提 D99 + 未提 ops.service namespace
    drifting.write_text("\n".join([f"see `{target}`"] * 4))
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "SCAN_ROOTS", [tmp_path / "docs"])
    monkeypatch.setattr(mod, "SCAN_FILES", [])
    monkeypatch.setattr(
        mod, "APPROVED_DOCS", ["docs/approved/zw-brain-architecture.md"]
    )
    findings = mod._find_drift_candidates(
        "D99", {target}, set(), {"ops.service"}
    )
    # 应有 2 条：path 漂移 + namespace 漂移
    assert len(findings) == 2, f"expected 2 findings, got {findings}"
    assert any("namespace" in f for f in findings)
    assert any(target in f for f in findings)
