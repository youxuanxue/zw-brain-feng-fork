#!/usr/bin/env python3
"""check_agent_runtime_import_confinement.py — preflight 段 77 (D68)

D68 (2026-06-22) 单一模型（embedded 退役）：zw-brain 进程内**零** AgentRuntime SDK
依赖 —— AgentRuntime 作为独立进程服务被经 HTTP 驱动（http_client 纯 HTTP），能力
交互走 service.py facade + AGENT.yaml ``kind:api`` 回调已发布 API。本守卫把「zw_brain/
下不得出现 ``from agent_runtime`` SDK 导入」硬化为机械不变量，防 embedded 嵌入回潮。

判定规则：
    - 范围：zw_brain/ 下所有 .py 文件
    - 命中：直接 import AgentRuntime **SDK** —— 顶层模块名恰为 ``agent_runtime``：
        ``from agent_runtime[...] import ...`` / ``import agent_runtime[...]``
      （**不**含 zw-brain 自己的封装包 ``zw_brain.shared.agent_runtime``，其顶层是 zw_brain；
        也不含 ``importlib.util.find_spec("agent_runtime")`` 这类软探测——只盯 import 语句）
    - 允许文件：ALLOWED_SDK_IMPORTERS —— D68 embedded 退役后**为空**：zw_brain/ 下
      任何 `from agent_runtime` 即违规（含历史接缝 service.py/capability_provider.py，
      它们也已不 import SDK）。接缝若需扩面（重新允许某文件）须改 ALLOWED_SDK_IMPORTERS + PR 说明。

退出码：
    0 = 通过（zw_brain/ 下零 AgentRuntime SDK import）
    1 = 至少一个 zw_brain/ 文件直接 import AgentRuntime SDK

触发即违规如何处理：
    1. 不要 import AgentRuntime SDK——AR 是独立进程服务，经 service.py facade
       （run_agent_task_sync / start_agent_task_background / poll_agent_task /
       resume_agent_task / reset_agent_runtime）+ http_client（纯 HTTP）交互。
    2. 能力交互走 AGENT.yaml ``kind:api`` 工具回调 zw-brain 已发布 API，不在进程内碰 SDK。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ZW_BRAIN = REPO / "zw_brain"

# D68 单一模型（embedded 退役）：zw-brain 进程内**零** AgentRuntime SDK 依赖——
# AR 作为独立进程服务被经 HTTP 驱动（http_client 纯 HTTP）。故允许集为空：
# zw_brain/ 下任何 `from agent_runtime` 即违规（防嵌入回潮）。
ALLOWED_SDK_IMPORTERS: frozenset[str] = frozenset()

# 顶层模块名恰为 agent_runtime 的 import 语句（SDK）。
# 命中： from agent_runtime import X / from agent_runtime.runtime.models import Y
#        import agent_runtime / import agent_runtime.runtime as r
# 不命中：from zw_brain.shared.agent_runtime.service import ...（首段是 zw_brain，非 SDK）
#        # 注释里提到 agent_runtime（行首是 #，非 from/import）
_SDK_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+agent_runtime(?:\.|\s|$)")


def scan_text(text: str) -> list[tuple[int, str]]:
    """返回每条直接 import AgentRuntime SDK 的 (lineno, 去空白行文本)。"""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _SDK_IMPORT_RE.match(line):
            hits.append((lineno, line.strip()))
    return hits


def find_violations(
    zw_brain_dir: Path, repo_root: Path, allowed: frozenset[str]
) -> list[tuple[str, int, str]]:
    """扫 zw_brain_dir 下 .py，返回允许集外直接 import SDK 的 (rel_path, lineno, line)。"""
    violations: list[tuple[str, int, str]] = []
    for path in sorted(zw_brain_dir.rglob("*.py")):
        rel = path.relative_to(repo_root).as_posix()
        if rel in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in scan_text(text):
            violations.append((rel, lineno, line))
    return violations


def main() -> int:
    if not ZW_BRAIN.is_dir():
        print(f"[ar-import-confinement] skip: {ZW_BRAIN} not present")
        return 0

    violations = find_violations(ZW_BRAIN, REPO, ALLOWED_SDK_IMPORTERS)
    if violations:
        print(
            f"[ar-import-confinement] FAIL: {len(violations)} 处接缝外直接 import AgentRuntime SDK："
        )
        for rel, lineno, line in violations:
            print(f"  - {rel}:{lineno}  {line}")
        print()
        print("[ar-import-confinement] hint: D68 单一模型（embedded 退役）——zw-brain 进程内禁 import")
        print("[ar-import-confinement]       AgentRuntime SDK；AR 是独立进程服务，经 http_client（纯 HTTP）驱动。")
        print("[ar-import-confinement]       能力交互走 facade（service.py）+ AGENT.yaml kind:api 回调，不 import SDK。")
        return 1

    print("[ar-import-confinement] ok: zw_brain/ 零 AgentRuntime SDK 依赖（embedded 退役，纯 HTTP 单一模型）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
