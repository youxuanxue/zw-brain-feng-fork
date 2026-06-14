#!/usr/bin/env python3
"""Preflight segment 48 — BrainService must hold no cross-cutting bodies (Action E).

Action E lifted the 5 cross-cutting helpers + 5 state-sync helpers off
``BrainService`` into ``zw_brain/command/pipeline_ops.py`` and
``zw_brain/command/sync.py``. BrainService retains a one-line delegate shim
per migrated helper for backward compatibility; this preflight enforces:

  Group A — cross-cutting (pipeline_ops):
    _mutate / _invoke_traced_read / _emit_audit / _enqueue_anchor /
    _append_audit_feed / _record_capability_call
        ⇒ MUST be ≤ 8 statement-bodies delegating to pipeline_ops.X.

  Group B — state sync (sync.py):
    _persist / _sync_reference_tables / _sync_database_aggregates /
    _sync_state_views / _sync_request_todos
        ⇒ MUST be ≤ 3 statement-bodies delegating to sync.X.

  Group C — fully retired (must NOT exist on BrainService at all):
    _safe_json / _request_by_id / _delivery_by_id /
    _delivery_by_request_id / _find_api_resource / _package_by_id

What this guards against
------------------------
- Inline regression — someone re-adds the body of ``_emit_audit`` to
  BrainService instead of routing through ``pipeline_ops.emit_audit``.
- Mid-refactor partial migration — a method is moved into pipeline_ops
  but a hot-fix puts the body back on BrainService.
- Re-creation of retired Group C methods (forbidden by Action E).

What is allowed
---------------
- One-line delegate shims for Groups A and B (statements <= cap).
- Methods *not* in any of the three groups (any other private helper
  on BrainService is outside this segment's scope).

The body cap (8 for cross-cutting, 3 for state sync) accommodates the
required ``from zw_brain.command import pipeline_ops # noqa`` lazy
import line + a small set of construction lines for SkillContext etc.
Pure passthroughs are 2-3 statements; the upper bound is set to catch
re-introduced inline bodies (typically dozens of lines).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAIN_FILE = REPO_ROOT / "zw_brain" / "command" / "brain.py"
# Stable reference to the real file: unit tests override BRAIN_FILE with synthetic
# fixtures; ledger-staleness checks only apply against this canonical path.
_CANONICAL_BRAIN_FILE = REPO_ROOT / "zw_brain" / "command" / "brain.py"

# ── Dead private-shim detection (2026-06-14, Action E 续：死委托 shim 守卫) ──────
# 背景：Action E/H 把 BrainService 上的 helper 逐批抬到 pipeline_ops/sync/services，
# BrainService 保留一行委托 shim 作向后兼容。随调用方迁走，部分 `_`-前缀私有 shim
# 变成**零调用死委托**（既无 brain.py 内部 self.X 调用、也无 zw_brain/+tests/ 外部引用）。
# 这类死壳是 brain.py 持续膨胀的来源、且 MEMORY「~59 零调用死委托 shim 待独立 sweep」。
# 本守卫机械识别新增死 shim（计数可机械化），删除由 PR-6「死代码清账」承接。
#
# KNOWN_DEAD_SHIMS = 已知存量死 shim 基线台账（棘轮）：守卫**只拦净新增**死 shim。
# 台账内的留待清账提交删除；删后须从本台账移除（否则报「台账过期」）。
# 净零压力：新增死 shim 必须先删旧的或在 PR 描述说明，不得只往台账塞。
#
# 2026-06-14（PR-β 集成收口）：`_new_request_id` / `_delivery_task_id_for_request`
# 两条历史死 shim 已在同批清账提交中从 brain.py 删除 → 台账随之清空（守卫现仅拦净新增）。
KNOWN_DEAD_SHIMS: frozenset[str] = frozenset()

# 永不当死 shim 误判的方法名：dunder（__init__ 等由构造/协议调用，无显式 self.X）。
_DEAD_SHIM_NAME_EXEMPT = re.compile(r"^__\w+__$")


# Group A — cross-cutting helpers (pipeline_ops bodies). Shims constructed
# with SkillContext etc. may have up to 8 statements; pure passthroughs use 2.
CROSS_CUTTING_METHODS: dict[str, int] = {
    "_mutate": 8,
    "_invoke_traced_read": 8,
    "_emit_audit": 4,
    "_enqueue_anchor": 4,
    "_append_audit_feed": 4,
    "_record_capability_call": 4,
}

# Group B — state sync helpers (sync.py bodies). 2-3 statements.
STATE_SYNC_METHODS: dict[str, int] = {
    "_persist": 4,
    "_sync_reference_tables": 4,
    "_sync_database_aggregates": 4,
    "_sync_state_views": 4,
    "_sync_request_todos": 4,
}

# Group C — fully retired methods (must NOT exist on BrainService).
RETIRED_METHODS: frozenset[str] = frozenset({
    "_safe_json",
    "_request_by_id",
    "_delivery_by_id",
    "_delivery_by_request_id",
    "_find_api_resource",
    "_package_by_id",
})


def _is_brain_service_method(class_def: ast.ClassDef, fn: ast.FunctionDef) -> bool:
    """True when ``fn`` is a direct child of ``BrainService``."""
    return fn in class_def.body


def _self_attr_names(tree: ast.Module) -> set[str]:
    """brain.py 全树里所有 ``self.X`` 属性访问的属性名集合（内部调用面）。

    ``self._foo(...)`` / ``self._foo`` 都产生 ``Attribute(value=Name('self'), attr='_foo')``。
    某方法名不在此集合 ⇒ brain.py 内部无任何 self.X 引用（含调用与取属性）。
    方法 ``def`` 本身不产生 Attribute 节点，故不会自指为「被调用」。
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            names.add(node.attr)
    return names


def _externally_referenced(name: str) -> bool:
    """``name`` 是否在 zw_brain/ 或 tests/ 的**非 brain.py** .py 文件里出现（token 级）。

    保守判定（宁可漏报死壳、绝不误杀活方法）：任何提及——含 getattr/字符串派发/
    docstring——都算「有外部引用」。仅 brain.py 自身的定义行不计。
    """
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    for root in ("zw_brain", "tests"):
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if path == BRAIN_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pattern.search(text):
                return True
    return False


def dead_private_shims(tree: ast.Module, brain_class: ast.ClassDef) -> list[str]:
    """BrainService 上零内部调用(self.X 不出现) 且零外部引用 的 `_`-前缀私有方法。

    排除：dunder（__init__ 等）、Group A/B/C 具名方法（各自有专属判据，且 A/B shim
    被外部 pipeline_ops/sync 调用=活的）、10 个 public facade delegator（无 `_` 前缀，
    天然不在 `_`-扫描内）。返回死 shim 名列表（含台账内已知项 + 净新增）。
    """
    self_attrs = _self_attr_names(tree)
    named_groups = set(CROSS_CUTTING_METHODS) | set(STATE_SYNC_METHODS) | RETIRED_METHODS
    dead: list[str] = []
    for fn in brain_class.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        name = fn.name
        if not name.startswith("_"):
            continue  # public facade delegators 等：不在私有 shim 范围
        if _DEAD_SHIM_NAME_EXEMPT.match(name):
            continue  # dunder
        if name in named_groups:
            continue  # 已由 Group A/B/C 判据覆盖
        if name in self_attrs:
            continue  # brain.py 内部有 self.X 调用 = 活
        if _externally_referenced(name):
            continue  # zw_brain/+tests/ 有外部引用 = 活
        dead.append(name)
    return dead


def main() -> int:
    if not BRAIN_FILE.exists():
        print(f"[brain-no-cross-cutting] skip: {BRAIN_FILE} not present")
        return 0

    text = BRAIN_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    brain_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BrainService":
            brain_class = node
            break

    if brain_class is None:
        print("[brain-no-cross-cutting] FAIL: BrainService class not found in brain.py")
        return 1

    violations: list[str] = []
    cross_cutting_count = 0
    state_sync_count = 0

    for fn in brain_class.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        name = fn.name

        # Group C — retired methods must not exist
        if name in RETIRED_METHODS:
            violations.append(
                f"{BRAIN_FILE}:{fn.lineno}: `{name}` was retired by Action E "
                f"and must NOT be re-introduced on BrainService — call sites "
                f"should use deps.services.X / view.X.find_by_id / direct import."
            )
            continue

        # Group A
        if name in CROSS_CUTTING_METHODS:
            cap = CROSS_CUTTING_METHODS[name]
            if len(fn.body) > cap:
                violations.append(
                    f"{BRAIN_FILE}:{fn.lineno}: `{name}` has {len(fn.body)} body "
                    f"statements (cap {cap}); cross-cutting body must live in "
                    f"zw_brain/command/pipeline_ops.py — restore the shim shape."
                )
            else:
                cross_cutting_count += 1
            continue

        # Group B
        if name in STATE_SYNC_METHODS:
            cap = STATE_SYNC_METHODS[name]
            if len(fn.body) > cap:
                violations.append(
                    f"{BRAIN_FILE}:{fn.lineno}: `{name}` has {len(fn.body)} body "
                    f"statements (cap {cap}); state-sync body must live in "
                    f"zw_brain/command/sync.py — restore the shim shape."
                )
            else:
                state_sync_count += 1
            continue

    # Dead private-shim pass — 零内部调用 + 零外部引用的 `_`-前缀死委托 shim。
    dead = dead_private_shims(tree, brain_class)
    dead_set = set(dead)
    lineno_of = {
        fn.name: fn.lineno
        for fn in brain_class.body
        if isinstance(fn, ast.FunctionDef)
    }
    # 1) 净新增死 shim（不在基线台账）→ FAIL。
    for name in sorted(dead_set - KNOWN_DEAD_SHIMS):
        violations.append(
            f"{BRAIN_FILE}:{lineno_of.get(name, '?')}: `{name}` is a dead private shim "
            f"on BrainService (no internal self.{name} call, no reference in zw_brain/+tests/) "
            f"— delete it (call sites should use deps.services.X), or if it is a deliberate "
            f"future hook, register it in KNOWN_DEAD_SHIMS with a reason."
        )
    # 2) 台账过期：登记为死 shim 但现已不是死的（被删 / 重新有了调用方）→ FAIL（应清台账）。
    #    仅对**真实 canonical brain.py** 生效——合成 fixture（单测把 BRAIN_FILE 指向临时文件、
    #    其中不含台账内方法）不应误触发；台账核账只针对正典文件。
    if BRAIN_FILE == _CANONICAL_BRAIN_FILE:
        for name in sorted(KNOWN_DEAD_SHIMS - dead_set):
            violations.append(
                f"{BRAIN_FILE}: KNOWN_DEAD_SHIMS ledger entry `{name}` is no longer a dead shim "
                f"(removed, or regained a caller) — remove it from KNOWN_DEAD_SHIMS in "
                f"scripts/check_brain_no_cross_cutting.py to keep the baseline honest."
            )

    if violations:
        print(
            f"[brain-no-cross-cutting] FAIL: {len(violations)} cross-cutting / "
            f"state-sync / dead-shim invariant(s) violated in BrainService"
        )
        for v in violations[:25]:
            print(f"  {v}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        print()
        print("  hint: cross-cutting bodies live in zw_brain/command/pipeline_ops.py")
        print("        state-sync bodies live in zw_brain/command/sync.py")
        print("        retired methods (Group C) must NOT be re-added to BrainService.")
        print("        dead private shims (no caller anywhere) must be deleted, not parked.")
        return 1

    print(
        f"[brain-no-cross-cutting] OK: {cross_cutting_count} cross-cutting shim(s) + "
        f"{state_sync_count} state-sync shim(s); all Group C retired methods absent; "
        f"{len(KNOWN_DEAD_SHIMS)} known dead shim(s) in baseline (no net-new)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
