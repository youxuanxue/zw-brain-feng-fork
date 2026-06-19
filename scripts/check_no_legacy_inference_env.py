#!/usr/bin/env python3
"""check_no_legacy_inference_env.py — preflight 段 56（D36 retrofit 硬化）

D36 (2026-05-29) 决策：推理网关连接变量统一为 ``ZW_BRAIN_INFERENCE_*``，删除一切
``INSPUR_INFERENCE_*`` / ``AUTH_TOKEN`` / 裸 ``BASE_URL``/``MODEL`` 兜底（见 CLAUDE.md D36）。
此前守卫只在 client 层有负向测试（D36.c），**没有仓库级机械防线**阻止已退役的
``INSPUR_INFERENCE_*`` env 前缀在文档 / 配置里回潮——PR #160 即活案例
（差点把失效契约钉进证据源 + 运维债务文档，preflight 全绿却放过）。

本守卫：扫全仓 tracked 文件，禁止已退役 env 前缀字面量 ``INSPUR_INFERENCE_``。

allowlist（合法保留，按文件）：
  - ``CLAUDE.md``：D36 决策记录本身，必须命名旧前缀以记录 "renamed from"。
  - ``tests/integration/test_inference_client.py``：D36 负向守卫，故意 set 旧名证明被忽略。

不误伤承重的网关 host 标识 —— ``INSPUR_GATEWAY_MARKERS`` / ``inspur-inference-gateway``
不含子串 ``INSPUR_INFERENCE_``，天然不匹配（D36.c：env 变量前缀 vs 网关 host 身份是两个维度）。

退出码：
    0 = 无回潮（仅 allowlist 文件含该字面量）
    1 = 检出 allowlist 外的 ``INSPUR_INFERENCE_`` 字面量
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NEEDLE = "INSPUR_INFERENCE_"
ALLOWLIST: frozenset[str] = frozenset(
    {
        "CLAUDE.md",  # D36 决策记录速查：记录 "INSPUR_INFERENCE_* → ZW_BRAIN_INFERENCE_*" 改名
        "docs/decisions/decision-log.md",  # D64 — D36 全量条目（原 CLAUDE.md 内）随 D-索引移出，仍记旧前缀改名史
        "tests/integration/test_inference_client.py",  # D36 负向守卫：set 旧名证明被忽略
        "scripts/check_no_legacy_inference_env.py",  # 本守卫自身：needle 定义 + docstring 必含该字面量
    }
)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def main() -> int:
    hits: list[str] = []
    for rel in _tracked_files():
        if rel in ALLOWLIST:
            continue
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 二进制 / 不可读 —— env 前缀只会出现在文本文件
        for lineno, line in enumerate(text.splitlines(), 1):
            if NEEDLE in line:
                hits.append(f"{rel}:{lineno}: {line.strip()[:120]}")

    if hits:
        print(
            f"[no-legacy-inference-env] FAIL: 检出 {len(hits)} 处已退役 "
            f"`{NEEDLE}*` env 前缀回潮（D36 已收敛为 ZW_BRAIN_INFERENCE_*）："
        )
        for h in hits:
            print(f"  {h}")
        print(
            "  修复：连接变量改用 ZW_BRAIN_INFERENCE_GATEWAY_URL / "
            "ZW_BRAIN_INFERENCE_API_KEY / ZW_BRAIN_INFERENCE_MODEL；"
        )
        print(
            f"  若确属 D36 决策记录 / 负向守卫的合法引用，"
            f"把文件加入 {Path(__file__).name} ALLOWLIST 并在 PR 说明理由。"
        )
        return 1

    print(
        f"[no-legacy-inference-env] OK: 全仓无 allowlist 外的 `{NEEDLE}*` 残留"
        f"（allowlist {len(ALLOWLIST)} 文件）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
