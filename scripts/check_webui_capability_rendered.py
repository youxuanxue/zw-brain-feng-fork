#!/usr/bin/env python3
"""check_webui_capability_rendered.py — preflight 段 52（god's-eye retrofit 2026-05-29）

问题根因（#161 上帝视角穿透）：capability manifest 的 `compatibility` 含 "webui"
+ `product_scope.status == "live"` 表示「该能力声称在 WebUI 大堂供应」，但
`export_agent_contract.py --check` 只校验契约投影一致，**不校验真有 .vue/.ts 渲染
消费者**。结果：187 个 live+webui 能力里 107 个无任何渲染落点，全绿却没人看得见。

本守卫 = baseline 棘轮（仿段 32b full-scan-exemptions）：
  - 收集 status=live 且 compatibility 含 'webui' 的能力（读 registered/*.json，不依赖
    任何生成产物）。
  - 判定「webui 可达」= 下列任一非循环信号命中（2026-06-13 上帝视角复核 #273 升级判据，
    根治 debt render-guard-slug-grep-false-negative）：
      LIT slug 字面量：slug 出现在 zw-brain-web/src/**/*.{vue,ts}，排除生成产物
         （registry/pages.generated.ts 等）。直接派发消费。
      ROUTE 专属 REST 路由：能力经专属路由（非通用 /api/skills/<slug>，如 /api/snapshot）
         被前端消费——从 openapi `x-zwbrain-skill-id` 现取 slug→路由映射，路由串出现在 src
         即可达。WebUI 经单一 system.snapshot 胖快照(/api/snapshot)读数即此类，前端无 slug
         字面量 → LIT 看不到，但 ROUTE 认。
      PINNED 手写测试钉死**真实前端 surface**：有手写测试既出现该 slug、又在同窗口内
         断言一个 **zw-brain-web/src 下的非生成前端文件**（.vue 组件 / 路由 / composable，
         如 `... .vue").read_text` 或 `'@/pages/X.vue'`）——证明确有渲染消费者，
         slug-grep 因走专属路由/动态拼串看不到字面量、但人工测试钉死了真实 surface。
         **「测试断言 manifest 自身 compatibility 含 webui」不算 PINNED**（discover_skills()
         读的就是 manifest，断言 manifest=循环信号，等同 pages.generated.ts 由 manifest 生成，
         证明不了任何真实前端落点 — 2026-06-14 上帝视角复核坐实并根治该循环判据）。
  - 读豁免清单 scripts/webui_capability_rendered_exemptions.txt（净存量债务台账）：留作
    **NL 加速器 / 内置 Agent 工具可达**这一类——经通用 NL 派发触达、无 slug 字面量、亦无专属
    路由/契约测试锚（如 platform.docs.* 经内置 a-zw-platform-guide Agent）。这是守卫**设计内**
    的合理长期豁免，非「缺陷工作量」。
  - FAIL（净新增漂移）：某能力既非 webui 可达（LIT/ROUTE/PINNED 全不命中）又不在豁免清单。
  - FAIL（台账漂移）：豁免清单含已可达的 slug（过期，应删——ROUTE/PINNED 现能自动识别的别再挂豁免）
    或不存在的 slug。

退出码：0 = 通过；1 = 净新增漂移或台账漂移。

用法：
    ./scripts/check_webui_capability_rendered.py            # 校验
    ./scripts/check_webui_capability_rendered.py --print    # 仅打印当前 unreachable 集合（刷新台账用）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO / "zw_brain" / "capability_registry" / "registered"
WEB_SRC = REPO / "zw-brain-web" / "src"
EXEMPTIONS_FILE = REPO / "scripts" / "webui_capability_rendered_exemptions.txt"
OPENAPI_FILE = REPO / "zw_brain" / "entry" / "rest" / "openapi.json"
TESTS_DIR = REPO / "tests"

# 生成产物 / 契约投影：出现 slug 不算「人写的渲染消费者」。
GENERATED_EXCLUDES = ("pages.generated.ts",)
# 通用能力调用路由前缀；专属路由（如 /api/snapshot）才是 ROUTE 的非循环可达信号。
GENERIC_SKILL_PREFIX = "/api/skills/"
# 真实前端 surface 锚：手写测试里断言一个 zw-brain-web/src 下的**非生成**前端文件
# （.vue 组件 / 路由 / composable），证明确有渲染消费者。这是 PINNED 的**非循环**判据。
# 反例（不算 surface）：pages.generated.ts、registry/*.generated.* 等 manifest 生成产物。
_REAL_SURFACE_ANCHOR = re.compile(
    r"""zw-brain-web[/"'].*?src.*?\.(?:vue|ts)        # web/src 下的 .vue/.ts 文件路径
        | @/(?:pages|components|composables)/[\w/]+\.vue  # 形如 '@/pages/X.vue'
    """,
    re.VERBOSE,
)
# 生成产物路径出现在锚行里时不计为真实 surface（manifest→生成=循环信号）。
_GENERATED_PATH_HINT = re.compile(r"\.generated\.|pages\.generated|registry/")
# slug 字面量引用：测试里以字符串字面量提到某能力 slug（含点的能力 id，蛇形小写段）。
# 排除文件名样式（.ts/.vue/.spec.ts 等扩展名段，含驼峰）——只认能力 slug 形态。
_FILE_EXT_SEGMENTS = frozenset({"ts", "tsx", "vue", "js", "jsx", "py", "json", "md", "css", "spec"})
_SLUG_LITERAL = re.compile(r"[\"']([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)[\"']")


def _looks_like_capability_slug(token: str) -> bool:
    """含点 token 是能力 slug 形态（非文件名）：末段不是源码扩展名。"""
    return token.rsplit(".", 1)[-1] not in _FILE_EXT_SEGMENTS


def live_webui_slugs() -> list[str]:
    out: list[str] = []
    for f in sorted(MANIFEST_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        scope = d.get("product_scope", {})
        if scope.get("status") == "live" and "webui" in d.get("compatibility", []):
            out.append(d["slug"])
    return out


def appears_in_src(needle: str) -> bool:
    """needle 字面量是否出现在 zw-brain-web/src 的 .vue/.ts（排除生成产物）。"""
    if not WEB_SRC.is_dir():
        return False
    proc = subprocess.run(
        ["grep", "-rl", "--include=*.vue", "--include=*.ts", needle, str(WEB_SRC)],
        capture_output=True,
        text=True,
    )
    files = [
        line
        for line in proc.stdout.splitlines()
        if line and not any(ex in line for ex in GENERATED_EXCLUDES)
    ]
    return len(files) > 0


def dedicated_routes() -> dict[str, str]:
    """slug → 专属 REST 路由（非通用 /api/skills/<slug>），从 openapi `x-zwbrain-skill-id` 现取。

    WebUI 经专属路由消费的能力前端无 slug 字面量（如 useSnapshot.ts 走 /api/snapshot）——
    这是非循环的 webui 可达信号（ROUTE）。映射现取，新增专属路由自动覆盖、无硬编码。
    """
    if not OPENAPI_FILE.is_file():
        return {}
    spec = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for path, ops in spec.get("paths", {}).items():
        if path.startswith(GENERIC_SKILL_PREFIX) or not isinstance(ops, dict):
            continue
        for op in ops.values():
            if isinstance(op, dict) and op.get("x-zwbrain-skill-id"):
                out[op["x-zwbrain-skill-id"]] = path
    return out


def contract_pinned_webui() -> set[str]:
    """有手写测试钉死该 slug 的**真实前端 surface** 的能力（PINNED，非循环判据）。

    走专属路由/动态拼串的能力前端无 slug 字面量（LIT 看不到），但若有手写测试**既**提到
    该 slug **又**在同窗口断言一个 zw-brain-web/src 下的非生成前端文件（.vue/路由/composable），
    即证明确有渲染消费者 → 钉死。

    **拒绝循环锚**：旧实现把「测试断言 manifest 的 compatibility 含 webui」当 PINNED——
    但 discover_skills() 读的就是 manifest，断言 manifest 等同 pages.generated.ts（由 manifest
    生成），证明不了任何真实前端落点（2026-06-14 上帝视角复核坐实）。本实现只认**真实 surface
    文件**锚，不认 compatibility 断言。

    判定：扫 tests/*.py 每个含真实 surface 锚行的文件——某 slug 字面量在锚行 ±N 行窗口内出现 → 钉死。
    surface 锚行若同时命中生成产物路径（.generated/registry）则不计（循环信号）。
    """
    if not TESTS_DIR.is_dir():
        return set()
    pinned: set[str] = set()
    window = 12
    for f in TESTS_DIR.glob("*.py"):
        # 守卫自测/回潮锁文件本身不当证据来源（避免「测守卫的测试」反向喂养 PINNED）。
        if f.name == "test_webui_capability_render_guard.py":
            continue
        lines = f.read_text(encoding="utf-8").splitlines()
        anchor_rows = [
            i
            for i, line in enumerate(lines)
            if _REAL_SURFACE_ANCHOR.search(line) and not _GENERATED_PATH_HINT.search(line)
        ]
        if not anchor_rows:
            continue
        for row in anchor_rows:
            lo = max(0, row - window)
            hi = min(len(lines), row + window + 1)
            for slug in _SLUG_LITERAL.findall("\n".join(lines[lo:hi])):
                if _looks_like_capability_slug(slug):
                    pinned.add(slug)
    return pinned


def reachability_index() -> tuple[dict[str, str], set[str]]:
    """一次性算出 ROUTE 路由映射 + PINNED 钉死集合，避免每 slug 重复解析。"""
    return dedicated_routes(), contract_pinned_webui()


def is_reachable(slug: str, routes: dict[str, str], pinned: set[str]) -> bool:
    """webui 可达 = LIT slug 字面量 ∪ ROUTE 专属路由在 src ∪ PINNED 契约测试钉死。"""
    if appears_in_src(slug):  # LIT
        return True
    route = routes.get(slug)  # ROUTE
    if route and appears_in_src(route):
        return True
    return slug in pinned  # PINNED


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
    routes, pinned = reachability_index()
    unreached = {s for s in slugs if not is_reachable(s, routes, pinned)}

    if "--print" in sys.argv:
        for s in sorted(unreached):
            print(s)
        return 0

    exempt = load_exemptions()

    # 1) 净新增漂移：unreachable 且未登记
    new_drift = sorted(unreached - exempt)
    # 2) 台账漂移：豁免登记了已可达的 slug（应删）或不存在的 slug
    all_slugs = set(slugs)
    stale_exempt = sorted(s for s in exempt if s in all_slugs and s not in unreached)
    ghost_exempt = sorted(s for s in exempt if s not in all_slugs)

    errors = 0
    if new_drift:
        errors += len(new_drift)
        print("  FAIL: 以下 live+webui 能力无任何 webui 可达信号（LIT slug / ROUTE 专属路由 / PINNED 契约测试），且未登记豁免（净新增「声称UI无渲染」漂移）：")
        for s in new_drift:
            print(f"    - {s}")
        print("  → 接面板渲染它（LIT）/ 给专属路由前端消费（ROUTE）/ 加契约测试钉死 webui（PINNED），或登记 NL 可达豁免进 scripts/webui_capability_rendered_exemptions.txt（附理由）。")
    if stale_exempt:
        errors += len(stale_exempt)
        print("  FAIL: 以下 slug 现已被 LIT/ROUTE/PINNED 自动识别为 webui 可达，豁免登记过期，应从台账删除：")
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
        f"  ok: live+webui={len(slugs)}；webui 可达(LIT/ROUTE/PINNED)={len(slugs) - len(unreached)}；"
        f"NL 可达豁免={len(unreached)}（见 docs/webui-capability-render-debt.md）；净新增漂移=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
