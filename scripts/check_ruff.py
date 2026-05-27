#!/usr/bin/env python3
# 提交期 ruff 守卫 — 与 CI lint (ruff) job 对齐，避免 F821/F401/I001/E402 等本可机械化检查
# 漂移到 CI 才发现（PR #86 F1 拆分批次正是因此暴露 82 处 F821 undefined-name 风险）。

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _find_ruff() -> str | None:
    venv = REPO_ROOT / ".venv" / "bin" / "ruff"
    if venv.is_file():
        return str(venv)
    return shutil.which("ruff")


def main() -> int:
    ruff = _find_ruff()
    if ruff is None:
        # PR #124 review 暴露：silent skip 让 16 个 I001 import-order 错误漂过本地门禁
        # 直到 CI 才挡下——正是本脚本头注释要避免的反模式。改为 fail-with-hint：
        # 默认硬挡，dev 显式 opt-out 才放过。
        if os.environ.get("ZW_BRAIN_PREFLIGHT_SKIP_RUFF") == "1":
            print("[ruff] skip: ruff not installed; ZW_BRAIN_PREFLIGHT_SKIP_RUFF=1 explicit opt-out")
            return 0
        print("[ruff] FAIL: ruff not installed (no .venv/bin/ruff and not on PATH)")
        print("  hint: 安装 — `uv sync --extra dev` 或 `pip install ruff`")
        print("  hint: 仅本机临时跳过 — `export ZW_BRAIN_PREFLIGHT_SKIP_RUFF=1`")
        print("  rationale: silent skip 曾让 PR #124 16 个 I001 错误漂到 CI（PR review 暴露）")
        return 1
    result = subprocess.run([ruff, "check", "."], cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print("[ruff] FAIL:")
        print(result.stdout)
        if result.stderr.strip():
            print(result.stderr)
        return 1
    print("[ruff] OK: ruff check 全通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
