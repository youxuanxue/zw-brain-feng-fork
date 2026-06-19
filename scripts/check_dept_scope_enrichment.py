#!/usr/bin/env python3
"""check_dept_scope_enrichment.py — preflight 段 71（部门数据收口完整性防回归）.

部门数据隔离（D61）靠**逐面手工**把部门可见域透传给 ``enrich_*`` 投影函数：消费侧每调一个
承载机构行的 enrich，就得显式带上部门收口 kwarg（``visible_org_codes=`` 或 ``dept_scoped=``）。
历史上这条「每加一个读面都记得透传」的纪律靠自觉——而 **#296 漏了 delivery_tasks、#297 漏了
工作台待办**，正是「新加/改读面忘传收口 kwarg → 不同部门用户看到彼此的数据」这类回归。今天唯一
org 相关守卫是段 70（只管写死机构码字面量），**没有任何守卫**保证读面透传完整。本守卫把这条
纪律机械化（CLAUDE.md §5：靠自觉反复犯的错必须硬化）。

可机械化的判据有两条，本守卫只做这两条；「某个面该不该收口」是语义判断，留人 GATE：

1. **must-scope 清单（GATE 人审记录，脚本内单源常量 MUST_SCOPE_ENRICH）**——每条 =
   一个承载机构行、必须按部门收口的 enrich 面 + 它承载部门收口的 kwarg 名。判定一个面是否
   org-capable 的客观依据 = **该 enrich 函数签名是否带 ``visible_org_codes`` 或 ``dept_scoped``
   形参**（带 = 能按机构/部门过滤行，必须收口；不带如 zones / discovery_resources 是全局发现面，
   by design 不收口、显式登记在 GLOBAL_BY_DESIGN）。

2. **两道 FAIL（任一即 exit 1）**：
   (a) 某 must-scope enrich 的**调用点没显式带它的收口 kwarg**（=忘透传，#296/#297 复发面）；
   (b) 存在一个**签名带收口形参（org-capable）的 enrich 面，却既不在 must-scope 清单、也不在
       GLOBAL_BY_DESIGN 豁免**（=新增了 org 能力面没登记 → 强制人来 GATE：登记为收口面 or
       显式豁免，不许默默加一个能按机构过滤却没人审过收口口径的面）。

「调用点带没带 kwarg」「org-capable 面是否都登记」可机械化由本脚本承载；「该不该收口 / 收口
口径对不对」是不可化约的语义判断，留 GATE 评审（CLAUDE.md 可机械化边界原则）。

Exit 0 = PASS；1 = 至少一条违例。``--self-test`` 跑自带回归断言。
接入：scripts/preflight.sh 段 71。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOMAIN_ROOT = REPO / "zw_brain" / "domain"
# 调用面扫描根：消费侧 handler（system_ops 6 面 + workbench 第 7 面），并全仓兜底扫别处调用点。
HANDLER_ROOT = REPO / "zw_brain" / "command"

# ── 部门收口 kwarg：承载「按机构/部门过滤行」语义的形参名 ──
# visible_org_codes：可见机构码集（None=全局 / 集=本机构+下级 / 空集=fail-closed）。
# dept_scoped：交付任务随其申请单收口的布尔开关（delivery_tasks 用此形参而非 visible_org_codes）。
SCOPE_KWARGS = ("visible_org_codes", "dept_scoped")

# ── must-scope 清单（GATE 人审记录）：enrich 函数名 -> 它承载部门收口的 kwarg ──
# 每条都经实际读源码签名确认带该形参（org-capable，承载机构行，必须逐调用点透传收口）。
# 新增 org-capable enrich 面须人审后登记进此 dict（or 进 GLOBAL_BY_DESIGN 显式豁免），否则 FAIL(b)。
MUST_SCOPE_ENRICH: dict[str, str] = {
    "enrich_provider_snapshot": "visible_org_codes",       # 供数侧 inbox（owner_org_id 收口）
    "enrich_disputes_snapshot": "visible_org_codes",       # 异议（complainant/provider_org 收口）
    "enrich_requests_snapshot": "visible_org_codes",       # 申请（applicant_org∨provider_org 收口）
    "enrich_approvals_snapshot": "visible_org_codes",      # 审批 R11（provider org 收口）
    "enrich_workbench_backlog": "visible_org_codes",       # 工作台待办（管理员审核待办收口，#297 漏面）
    "enrich_delivery_tasks_snapshot": "dept_scoped",       # 交付任务（随申请单收口，#296 漏面）
}

# ── 全局面 by design（org-capable=否，签名不带收口形参，登记为豁免，免 FAIL(b) 误报）──
# 发现/共享市场永久全局（承 D60/D53①/D61①）：跨部门共享市场，刻意不按部门收口。
GLOBAL_BY_DESIGN: frozenset[str] = frozenset(
    {
        "enrich_zones_snapshot",                # P7 专区卡（全局）
        "enrich_discovery_resources_snapshot",  # 发现/找数据资源（全局）
    }
)

# enrich 函数定义行：`def enrich_xxx(`。
DEF_RE = re.compile(r"^\s*def (enrich_[A-Za-z0-9_]+)\s*\(")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def _discover_enrich_signatures() -> dict[str, bool]:
    """扫 domain/ 下所有 ``def enrich_*``，返回 {函数名: 是否带部门收口形参}。

    形参检测：从 def 行起读到该函数签名括号配平那一行（即完整签名区间，支持多行签名），
    检查签名文本里是否出现任一 SCOPE_KWARG 作为形参。判据用「kwarg 名 + 紧跟 `:`/`,`/`)`/`=`」
    的形参形态，避免把 docstring/注释里提及的同名词误判（签名区间天然不含 docstring）。
    """
    sigs: dict[str, bool] = {}
    if not DOMAIN_ROOT.exists():
        return sigs
    for path in sorted(DOMAIN_ROOT.rglob("*.py")):
        lines = _read(path).splitlines()
        i = 0
        n = len(lines)
        while i < n:
            m = DEF_RE.match(lines[i])
            if not m:
                i += 1
                continue
            fn = m.group(1)
            # 收集完整签名：从 def 行累积到括号配平（`(` 出现过且 paren 计数归零）那一行。
            sig_text = ""
            depth = 0
            started = False
            j = i
            while j < n:
                ln = lines[j]
                sig_text += ln + "\n"
                depth += ln.count("(") - ln.count(")")
                started = started or "(" in ln
                j += 1
                if started and depth <= 0:
                    break
            has_scope = any(
                re.search(rf"\b{re.escape(kw)}\s*[:=,)]", sig_text) for kw in SCOPE_KWARGS
            )
            sigs[fn] = has_scope
            i = j
    return sigs


def _find_call_sites(fn: str) -> list[tuple[str, int, str]]:
    """全仓（command/ 下）找 ``fn(`` 调用点，返回 [(rel_path, lineno, 完整调用文本)]。

    多行调用：从 `fn(` 行起累积到括号配平，得到完整 args 文本（含跨行 kwargs）。
    跳过 import 行（`import fn` / `from … import` 续行里的裸名）与注释——
    只认 `fn(` 紧跟左括号的真实调用形态。
    """
    sites: list[tuple[str, int, str]] = []
    call_re = re.compile(rf"\b{re.escape(fn)}\s*\(")
    for path in sorted(HANDLER_ROOT.rglob("*.py")):
        lines = _read(path).splitlines()
        rel = path.relative_to(REPO).as_posix()
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.lstrip()
            # 跳过 import / 注释行（避免把 `enrich_requests_snapshot,` 这种 import 续行误当调用）。
            if stripped.startswith(("import ", "from ", "#")):
                i += 1
                continue
            if not call_re.search(line):
                i += 1
                continue
            # 累积完整调用文本到括号配平。
            call_text = ""
            depth = 0
            j = i
            started = False
            while j < n:
                ln = lines[j]
                call_text += ln + "\n"
                depth += ln.count("(") - ln.count(")")
                started = started or "(" in ln
                j += 1
                if started and depth <= 0:
                    break
            sites.append((rel, i + 1, call_text))
            i = j
    return sites


def _call_passes_kwarg(call_text: str, kwarg: str) -> bool:
    """调用文本里是否显式带了 `kwarg=`（关键字实参）。"""
    return re.search(rf"\b{re.escape(kwarg)}\s*=", call_text) is not None


def _run_repo() -> int:
    sigs = _discover_enrich_signatures()
    violations: list[str] = []

    # ── FAIL(b)：org-capable 面（签名带收口形参）必须登记在 must-scope 或 global-by-design ──
    registered = set(MUST_SCOPE_ENRICH) | set(GLOBAL_BY_DESIGN)
    for fn, has_scope in sorted(sigs.items()):
        if has_scope and fn not in registered:
            violations.append(
                f"[未登记 org-capable 面] {fn}() 签名带部门收口形参"
                f"（{'/'.join(SCOPE_KWARGS)} 之一），却既不在 MUST_SCOPE_ENRICH 也不在 GLOBAL_BY_DESIGN。"
                "新增能按机构/部门过滤行的读面必须人审后登记：要收口→进 MUST_SCOPE_ENRICH 并列其收口 kwarg；"
                "若 by design 全局→进 GLOBAL_BY_DESIGN。"
            )

    # 反向核对：must-scope 清单里的面应当真的存在且确实带收口形参（清单不漂移）。
    for fn, kwarg in sorted(MUST_SCOPE_ENRICH.items()):
        if fn not in sigs:
            violations.append(
                f"[清单漂移] MUST_SCOPE_ENRICH 列了 {fn}()，但 domain/ 下找不到其定义"
                "（函数被改名/删除？请同步更新清单）。"
            )
        elif not sigs[fn]:
            violations.append(
                f"[清单漂移] MUST_SCOPE_ENRICH 列 {fn}() 的收口 kwarg='{kwarg}'，"
                f"但其签名已不带任何收口形参（{'/'.join(SCOPE_KWARGS)}）——收口能力被移除？请同步更新清单。"
            )

    # ── FAIL(a)：每个 must-scope enrich 的每个调用点都必须显式带其收口 kwarg ──
    for fn, kwarg in sorted(MUST_SCOPE_ENRICH.items()):
        for rel, lineno, call_text in _find_call_sites(fn):
            if not _call_passes_kwarg(call_text, kwarg):
                violations.append(
                    f"[漏透传] {rel}:{lineno} 调用 {fn}() 未显式带部门收口 kwarg `{kwarg}=`。"
                    f"部门隔离（D61）靠逐面透传——此调用点须显式传 {kwarg}=（全局角色→None/False 由"
                    " ReferenceService.visible_org_codes 算出，部门角色→本机构集/True），否则不同部门用户"
                    "会看到彼此的数据（#296 漏 delivery_tasks、#297 漏工作台待办即此回归）。"
                )

    if violations:
        print(
            "[dept-scope-enrichment] FAIL — 部门数据收口完整性违例（承 D61 / #296 / #297）：",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    n_must = len(MUST_SCOPE_ENRICH)
    n_global = len(GLOBAL_BY_DESIGN)
    n_capable = sum(1 for v in sigs.values() if v)
    print(
        f"[dept-scope-enrichment] OK：{n_must} 个 must-scope enrich 面调用点均显式透传部门收口 kwarg；"
        f"{n_capable} 个 org-capable 面全部登记（{n_must} 收口 + {n_global} 全局豁免）。"
    )
    return 0


def _self_test() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    # _call_passes_kwarg：带 / 不带 kwarg。
    check(
        "passes-visible",
        _call_passes_kwarg("enrich_requests_snapshot(s, visible_org_codes=v)", "visible_org_codes"),
    )
    check(
        "missing-visible",
        not _call_passes_kwarg("enrich_requests_snapshot(s, tenant_id=t)", "visible_org_codes"),
    )
    check(
        "passes-dept-scoped",
        _call_passes_kwarg("enrich_delivery_tasks_snapshot(t, dept_scoped=True)", "dept_scoped"),
    )
    check(
        "missing-dept-scoped",
        not _call_passes_kwarg("enrich_delivery_tasks_snapshot(t, request_map=m)", "dept_scoped"),
    )

    # 签名检测：带形参 / 不带形参（用真实多行签名形态）。
    sig_with = (
        "def enrich_x_snapshot(\n    snapshot, *, tenant_id=None,\n"
        "    visible_org_codes: set | None = None, copy: bool = True,\n) -> dict:\n"
    )
    sig_without = "def enrich_zones_snapshot(\n    snapshot, *, tenant_id=None, copy=True\n) -> dict:\n"

    def _has_scope(sig: str) -> bool:
        return any(re.search(rf"\b{re.escape(kw)}\s*[:=,)]", sig) for kw in SCOPE_KWARGS)

    check("sig-detect-with", _has_scope(sig_with))
    check("sig-detect-without", not _has_scope(sig_without))
    # docstring 里提 visible_org_codes 但签名不带，不应误判（签名区间不含 docstring）。
    sig_doc_only = "def enrich_zones_snapshot(s, *, copy=True):"
    check("sig-no-falsepos-docstring", not _has_scope(sig_doc_only))

    # 清单/豁免不相交，且都非空。
    check("lists-disjoint", not (set(MUST_SCOPE_ENRICH) & set(GLOBAL_BY_DESIGN)))
    check("must-scope-nonempty", len(MUST_SCOPE_ENRICH) > 0)
    # 每个 must-scope 的 kwarg 都是已知收口 kwarg。
    check("kwargs-known", all(kw in SCOPE_KWARGS for kw in MUST_SCOPE_ENRICH.values()))

    if failures:
        print(f"[dept-scope-enrichment --self-test] FAIL: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("[dept-scope-enrichment --self-test] OK: 11 self-test assertions passed.")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    return _run_repo()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
