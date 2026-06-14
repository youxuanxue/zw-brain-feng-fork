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
- **机械自发现**（2026-06-14，名实相符根治）：rglob ``scripts/*.py`` 找出**所有**调用
  ``register_grep_guard(`` 的守卫模块并 import，不再硬编码 2 个白名单。新增 grep 守卫
  ``register_grep_guard`` 后**自动纳入**对账——无需任何手工登记。此前硬编码只覆盖 2/8 个
  register_grep_guard 调用方（check_grep_guards_batch 的 3 段 / check_adapter_write_ban
  从未被元守卫看过），是「元守卫自身扫描面漂移」——守卫漏掉守卫，与本元守卫立设动因同构。
- 豁免须带理由文本（``SURFACE_EXEMPTIONS`` 值非空），防「一豁免了之」。

退出码：0 = 无未覆盖主流扩展名；1 = 存在守卫面漂移。
接入：scripts/preflight.sh 段 26b。
"""
from __future__ import annotations

import importlib
import re
import sys

from guard_lib import iter_files, registered_surfaces, repo_root

REPO = repo_root()
SCRIPTS_DIR = REPO / "scripts"

# 机械自发现的排除项：本元守卫自身 + 库（只定义 register_grep_guard，不是守卫）。
_DISCOVERY_EXCLUDE = frozenset({"check_guard_scan_surface", "guard_lib"})
# 实际**调用** register_grep_guard(...) 的特征（排除 import / 定义行）。
_REGISTER_CALL = re.compile(r"register_grep_guard\s*\(")


def discover_meta_guards() -> tuple[str, ...]:
    """rglob scripts/*.py，机械找出所有调用 register_grep_guard(...) 的守卫模块名。

    名实相符：守卫一旦 ``register_grep_guard`` 即自动纳入元守卫对账，无需手工登记
    （旧硬编码白名单只覆盖 2/8，是元守卫自身的扫描面漂移）。
    """
    found: list[str] = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        stem = path.stem
        if stem in _DISCOVERY_EXCLUDE:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # 必须有真实调用行（非仅 `from guard_lib import register_grep_guard` / 注释提及）。
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith("from ") or stripped.startswith("import "):
                continue
            if _REGISTER_CALL.search(line):
                found.append(stem)
                break
    return tuple(found)


# import 即注册：自动发现的全部 register_grep_guard 调用方（机械、非硬编码）。
GUARDS_UNDER_META = discover_meta_guards()

# 主流源码扩展名——守卫漏掉这些才构成真风险（UI/逻辑/后端代码都在这几类里）。
TRACKED_SOURCE_EXTS = (".py", ".ts", ".tsx", ".vue", ".js", ".jsx")

# 显式豁免表：{(guard_name, ext): "理由"}。某守卫**故意**不覆盖某 root 下的某扩展名时
# 在此带理由登记（值必须非空）。
SURFACE_EXEMPTIONS: dict[tuple[str, str], str] = {
    # no-legacy-role-codes 的正则 `\b[rR][1-8]\b` 在 .ts/.vue 里命中的 22 处全是**架构 R-约束 /
    # D-决策子锚点**引用（如 `D57②/R8`、`链路1（R1/R2/R3）`），与已退役的旧**用户角色码** R1-R8
    # 同名异 namespace。该守卫在 .py/.md 上靠 LEGACY_ALLOWED_LINE_MARKERS 逐条标注消解此歧义；
    # 强扩到前端会引入 22 条纯架构引用误报、要逐行加 marker 维护——属过度机械化误报负债（§77）。
    # 前端不承载旧用户角色码字面（角色经 policy.py 7 码 + role_codes.py，前端只引 ROLE_* 常量名），
    # 故 .ts/.vue 故意不纳入本守卫面。
    ("no-legacy-role-codes", ".ts"): "R[1-8] 在前端=架构 R-约束/D-决策锚点(非旧用户角色码)，同名异 namespace；强扫=22 条纯引用误报负债(§77)",
    ("no-legacy-role-codes", ".vue"): "R[1-8] 在前端=架构 R-约束/D-决策锚点(非旧用户角色码)，同名异 namespace；强扫=22 条纯引用误报负债(§77)",
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
