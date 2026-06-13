#!/usr/bin/env python3
"""check_guard_scan_surface.py — preflight 段 26b（元守卫：守卫面漂移防御）.

§5 升级原则的本期标的。**头号缺陷类**：「守卫还在跑、但扫描面落后于代码演进」——
守卫绿不等于守卫有效。实证：R12 `check_ui_term_blacklist` 长期只扫 `.html/.js/.css`，
而前端早已迁到 57 个 `.vue`，于是「全清」是**假绿**——57 个 .vue 从未被这条守卫看过。
机械门禁一旦扫描面漂移就静默失效，没有任何信号。

本元守卫对账「守卫**声明的**扫描面」vs「git ls-files **实际存在的**文件类型分布」：
对每个注册了 ``register_grep_guard(roots, extensions)`` 的 grep 类守卫，若其某个目标
root 下存在**主流源码扩展名**（.vue/.ts/.py 等）却**不在**该守卫声明的 extensions 里，
即 FAIL——除非该 (guard, ext) 在显式豁免表 ``SURFACE_EXEMPTIONS`` 中带理由登记。

设计取舍（务实）：
- 只盯**主流源码扩展名**（``TRACKED_SOURCE_EXTS``）——守卫漏掉这些才是真风险；
  .json/.md/.yaml 等数据/文档扩展名不强制每个守卫都覆盖（覆盖与否是守卫语义选择）。
- 先对两个高价值守卫生效（R12 ui-term / D6 no-direct-llm）；新增 grep 守卫
  ``register_grep_guard`` 后自动纳入对账（``GUARDS_UNDER_META`` 登记）。
- 豁免须带理由文本（``SURFACE_EXEMPTIONS`` 值非空），防「一豁免了之」。

退出码：0 = 无未覆盖主流扩展名；1 = 存在守卫面漂移。
接入：scripts/preflight.sh 段 26b。
"""
from __future__ import annotations

import importlib
import sys

from guard_lib import iter_files, registered_surfaces, repo_root

REPO = repo_root()

# 触发各守卫的 register_grep_guard（import 即注册）。新增受元守卫监管的 grep 守卫
# 在此登记其模块名即可。
GUARDS_UNDER_META = (
    "check_ui_term_blacklist",   # R12
    "check_no_direct_llm",       # D6
)

# 主流源码扩展名——守卫漏掉这些才构成真风险（UI/逻辑/后端代码都在这几类里）。
TRACKED_SOURCE_EXTS = (".py", ".ts", ".tsx", ".vue", ".js", ".jsx")

# 显式豁免表：{(guard_name, ext): "理由"}。某守卫**故意**不覆盖某 root 下的某扩展名时
# 在此带理由登记（值必须非空）。当前为空——两个高价值守卫已覆盖其 root 下全部主流扩展名。
SURFACE_EXEMPTIONS: dict[tuple[str, str], str] = {
    # 例：("ui-term-blacklist", ".py"): "R12 只管前端用户面，后端 .py 不在 zw-brain-web/ root"
    # （注：root 限定已天然排除——zw-brain-web/ 下本就没有 .py；此处仅示范豁免写法）
}


def _exts_present_in_roots(roots: tuple[str, ...]) -> dict[str, list[str]]:
    """返回 {ext: [示例相对路径,...]}，限定在 roots 下（roots=() → 全仓）的受跟踪文件。"""
    present: dict[str, list[str]] = {}
    search_roots = roots or None
    for path in iter_files(extensions=TRACKED_SOURCE_EXTS, roots=search_roots):
        rel = path.relative_to(REPO).as_posix()
        present.setdefault(path.suffix, [])
        if len(present[path.suffix]) < 3:
            present[path.suffix].append(rel)
    return present


def main() -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    for mod in GUARDS_UNDER_META:
        try:
            importlib.import_module(mod)
        except ImportError as exc:
            print(f"[guard-scan-surface] FAIL: 无法 import 受监管守卫模块 {mod}：{exc}", file=sys.stderr)
            return 1

    surfaces = registered_surfaces()
    drift: list[str] = []
    checked = 0
    for name, surface in sorted(surfaces.items()):
        declared = set(surface.extensions)
        present = _exts_present_in_roots(surface.roots)
        for ext, samples in sorted(present.items()):
            if ext in declared:
                continue
            if (name, ext) in SURFACE_EXEMPTIONS and SURFACE_EXEMPTIONS[(name, ext)].strip():
                continue
            checked += 1
            roots_label = ", ".join(surface.roots) if surface.roots else "(全仓)"
            drift.append(
                f"  守卫 `{name}`（root: {roots_label}）声明扫描 {sorted(declared)}，"
                f"但 root 下存在未覆盖的主流源码扩展名 `{ext}`"
                f"（{len(present[ext])}+ 文件，例：{', '.join(samples)}）"
            )

    if drift:
        print("[guard-scan-surface] FAIL: 守卫面漂移（守卫在跑但扫描面落后于代码演进）：", file=sys.stderr)
        for d in drift:
            print(d, file=sys.stderr)
        print(
            "\nfix：把该扩展名加进守卫的 EXTENSIONS（并 register_grep_guard 同步声明），"
            "\n或在 check_guard_scan_surface.SURFACE_EXEMPTIONS 带理由登记「故意不覆盖」。"
            "\n（守卫绿 ≠ 守卫有效——R12 漏 57 个 .vue 全清是本元守卫的设立动因。）",
            file=sys.stderr,
        )
        return 1

    print(
        f"[guard-scan-surface] OK: {len(surfaces)} 个注册守卫面无漂移"
        f"（主流源码扩展名 {list(TRACKED_SOURCE_EXTS)} 均被各守卫 root 内覆盖或带理由豁免）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
