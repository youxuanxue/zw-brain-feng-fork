#!/usr/bin/env python3
"""check_webui_capability_rendered.py — preflight 段 52（god's-eye retrofit 2026-05-29）

问题根因（#161 上帝视角穿透）：capability manifest 的 `compatibility` 含 "webui"
+ `product_scope.status == "live"` 表示「该能力声称在 WebUI 大堂供应」，但
`export_agent_contract.py --check` 只校验契约投影一致，**不校验真有 .vue/.ts 渲染
消费者**。结果：187 个 live+webui 能力里 107 个无任何渲染落点，全绿却没人看得见
（网关运行状态就是其一）。

本守卫 = baseline 棘轮（仿段 32b full-scan-exemptions）：
  - 收集 status=live 且 compatibility 含 'webui' 的能力（读 registered/*.json，不依赖
    任何生成产物）。
  - 判定「已渲染」= slug 字面量出现在 zw-brain-web/src/**/*.{vue,ts}，排除生成产物
    （registry/pages.generated.ts 等）。
  - 读豁免清单 scripts/webui_capability_rendered_exemptions.txt（净存量债务台账）。
  - FAIL（净新增漂移）：某能力 unconsumed 且不在豁免清单。
  - FAIL（台账漂移）：豁免清单含已被消费的 slug（过期，应删）或不存在的 slug。

诚实补充（写进 docs/webui-capability-render-debt.md）：字面量 grep 判定有假阴性——
部分能力经 NL 加速器 / 通用派发可达但页面无字面 slug；豁免清单是「疑似未渲染」，
还债 = 接面板 **或** 标注「NL 可达豁免理由」。

退出码：0 = 通过；1 = 净新增漂移或台账漂移。

用法：
    ./scripts/check_webui_capability_rendered.py            # 校验
    ./scripts/check_webui_capability_rendered.py --print    # 仅打印当前 unconsumed 集合（生成/刷新台账用）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO / "zw_brain" / "capability_registry" / "registered"
WEB_SRC = REPO / "zw-brain-web" / "src"
EXEMPTIONS_FILE = REPO / "scripts" / "webui_capability_rendered_exemptions.txt"

# 生成产物 / 契约投影：出现 slug 不算「人写的渲染消费者」。
GENERATED_EXCLUDES = ("pages.generated.ts",)


def live_webui_slugs() -> list[str]:
    out: list[str] = []
    for f in sorted(MANIFEST_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        scope = d.get("product_scope", {})
        if scope.get("status") == "live" and "webui" in d.get("compatibility", []):
            out.append(d["slug"])
    return out


def is_consumed(slug: str) -> bool:
    """slug 字面量是否出现在 zw-brain-web/src 的 .vue/.ts（排除生成产物）。"""
    if not WEB_SRC.is_dir():
        return False
    proc = subprocess.run(
        ["grep", "-rl", "--include=*.vue", "--include=*.ts", slug, str(WEB_SRC)],
        capture_output=True,
        text=True,
    )
    files = [
        line
        for line in proc.stdout.splitlines()
        if line and not any(ex in line for ex in GENERATED_EXCLUDES)
    ]
    return len(files) > 0


def load_exemptions() -> set[str]:
    if not EXEMPTIONS_FILE.is_file():
        return set()
    slugs: set[str] = set()
    for raw in EXEMPTIONS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            slugs.add(line)
    return slugs


def main() -> int:
    slugs = live_webui_slugs()
    unconsumed = {s for s in slugs if not is_consumed(s)}

    if "--print" in sys.argv:
        for s in sorted(unconsumed):
            print(s)
        return 0

    exempt = load_exemptions()

    # 1) 净新增漂移：unconsumed 且未登记
    new_drift = sorted(unconsumed - exempt)
    # 2) 台账漂移：豁免登记了已消费的 slug（应删）或不存在的 slug
    all_slugs = set(slugs)
    stale_exempt = sorted(s for s in exempt if s in all_slugs and s not in unconsumed)
    ghost_exempt = sorted(s for s in exempt if s not in all_slugs)

    errors = 0
    if new_drift:
        errors += len(new_drift)
        print("  FAIL: 以下 live+webui 能力无任何 .vue/.ts 渲染消费者，且未登记豁免（净新增「声称UI无渲染」漂移）：")
        for s in new_drift:
            print(f"    - {s}")
        print("  → 接面板渲染它，或登记进 scripts/webui_capability_rendered_exemptions.txt（附理由/待办）。")
    if stale_exempt:
        errors += len(stale_exempt)
        print("  FAIL: 以下 slug 已被页面消费，豁免登记过期，应从台账删除：")
        for s in stale_exempt:
            print(f"    - {s}")
    if ghost_exempt:
        errors += len(ghost_exempt)
        print("  FAIL: 以下豁免 slug 不在 live+webui 能力集合中（重命名/退役/拼写），应清理：")
        for s in ghost_exempt:
            print(f"    - {s}")

    if errors:
        return 1

    print(
        f"  ok: live+webui={len(slugs)}；已渲染={len(slugs) - len(unconsumed)}；"
        f"登记债务={len(unconsumed)}（见 docs/webui-capability-render-debt.md）；净新增漂移=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
