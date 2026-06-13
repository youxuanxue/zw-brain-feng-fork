"""test_trust_anchor_measurement.py — 测量信任锚守卫单测（R-001 / R-009）.

锁定两条修复，防回潮：
  R-001：capture 的 runner 汇总解析——退出码 0 但 passed==0（全 skip / no tests ran /
         全 deselected）一律记 vacuous-skip，绝不冒绿（fail-closed）。
  R-009：feature_fingerprint 纳入全局共享盐文件——改任一 helper 内容 → 指纹变 → 旧绿失效。

这些是测量轴的"诚实地基"：退出码假绿 + helper 弱化绕指纹，都会让 Done 在没真跑/被放水的
情况下保住。单测在此把它们钉死。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from capture_feature_status import _classify_e2e, _classify_pytest  # noqa: E402
from feature_status_lib import (  # noqa: E402
    GLOBAL_SALT_FILES,
    feature_fingerprint,
)


# ---------------------------------------------------------------- R-001 pytest
@pytest.mark.parametrize(
    "rc,out,expect",
    [
        (0, "5 passed, 2 skipped in 1.2s", "pass"),
        (0, "12 passed in 3.1s", "pass"),
        (0, "1 xpassed, 2 skipped in 0.2s", "pass"),  # xpassed 也算真通过
        (0, "3 skipped in 0.4s", "vacuous-skip"),  # 全 skip 退 0 → 不冒绿
        (0, "no tests ran in 0.01s", "vacuous-skip"),
        (0, "4 deselected in 0.1s", "vacuous-skip"),
        (1, "1 failed, 2 passed in 0.5s", "fail"),  # 退非零恒 fail
        (1, "errors in 0.1s", "fail"),
        (2, "", "fail"),  # 退非零、无汇总仍 fail
    ],
)
def test_classify_pytest_vacuous_skip_not_green(rc, out, expect):
    assert _classify_pytest(rc, out)[0] == expect


def test_real_pytest_module_classifies_pass(monkeypatch):
    """端到端回归（R-001 实现 bug）：用 capture 实际跑一个真模块，须判 pass。

    曾因 `pytest -q`（叠 pyproject addopts 的 `-q` = 双静默）在全绿短跑时吞掉末行汇总
    （输出只剩 `....[100%]`、无 'N passed'），_classify_pytest 抓不到 passed → 误判
    vacuous-skip，把全部 38 个真绿模块误降级。去掉显式 `-q`、改 `--tb=no` 后汇总恒打印。
    本测真跑确定性的 grant_revoke 模块（不依赖 e2e 栈），锁死"真绿不被误降级"。
    """
    from capture_feature_status import _run_module

    py312 = REPO / ".venv-py312" / "bin" / "python"
    if not py312.exists():  # 无 py312 环境的机器上跳过（本测意在 CI/本地有 venv 时守回归）
        pytest.skip("无 .venv-py312（本机环境），跳过真模块跑")
    monkeypatch.setenv("ZW_BRAIN_CAPTURE_PYTHON", str(py312))
    result, detail = _run_module("tests/test_wave1_j1_grant_revoke.py")
    assert result == "pass", f"真绿模块被误判 {result}：{detail}"


# ---------------------------------------------------------------- R-001 e2e
@pytest.mark.parametrize(
    "rc,out,expect",
    [
        (0, "5 passed (3.2s)", "pass"),
        (0, "  2 skipped\n  2 passed (4s)", "pass"),  # 混合有 passed → 绿
        (0, "4 skipped", "vacuous-skip"),  # 全 skip（如 national flag 未开）→ 不冒绿
        (0, "", "vacuous-skip"),  # 退 0 无任何 passed 行 → 不冒绿
        (1, "2 failed\n3 passed (5s)", "fail"),
    ],
)
def test_classify_e2e_vacuous_skip_not_green(rc, out, expect):
    assert _classify_e2e(rc, out)[0] == expect


# ---------------------------------------------------------------- R-009 salt
def test_salt_files_all_exist():
    """全局盐文件列表里每个文件都须真实存在——列表登记了不存在的文件即配置漂移。"""
    missing = [s for s in GLOBAL_SALT_FILES if not (REPO / s).is_file()]
    assert not missing, f"GLOBAL_SALT_FILES 登记了不存在的文件：{missing}"


def test_fingerprint_includes_shared_salt(tmp_path, monkeypatch):
    """改任一共享盐文件内容 → 同一 feature 的指纹必变（否则弱化 helper 能在指纹'新鲜'下保绿）。"""
    import feature_status_lib as lib

    # 造一个最小 .feature（无测试 ref，孤立出盐文件这一变量）。
    feat = tmp_path / "salt_probe.feature"
    feat.write_text(
        "# Owner: e1\n# Pytest: pending\nFeature: salt probe\n  Scenario: x\n",
        encoding="utf-8",
    )
    before = feature_fingerprint(feat)

    # 把第一个盐文件指向一个临时副本并改其内容：用 monkeypatch 改 REPO 根不现实，
    # 故改真实盐文件再还原（读字节→改→算→还原）。选体量小的 r12-forbidden-patterns.ts。
    salt_rel = "tests/e2e/r12-forbidden-patterns.ts"
    assert salt_rel in lib.GLOBAL_SALT_FILES
    salt_path = REPO / salt_rel
    original = salt_path.read_bytes()
    try:
        salt_path.write_bytes(original + b"\n// trust-anchor salt probe (transient)\n")
        after = feature_fingerprint(feat)
    finally:
        salt_path.write_bytes(original)

    assert before != after, "改共享盐文件后指纹未变 → R-009 未生效（helper 弱化绕过指纹）"
    # 还原后指纹回到原值（确定性）。
    assert feature_fingerprint(feat) == before
