"""段 26b 元守卫自发现回潮锁（覆盖 2/8 → 全量机械自发现，2026-06-14）。

锁住：受元守卫监管的 grep 守卫集合 = rglob scripts/*.py **机械自发现**所有
register_grep_guard 调用方（排除元守卫自身 + guard_lib 库），而非硬编码白名单。
防止有人退回手编 2-tuple → check_grep_guards_batch 的 3 段 / check_adapter_write_ban
再次「守卫在跑但从未被元守卫看过」（元守卫自身的扫描面漂移）。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

pytestmark = pytest.mark.no_db

# 元守卫裸 import guard_lib（约定 scripts/ 在 path）——加载前置 scripts/ 到 sys.path。
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "check_guard_scan_surface", SCRIPTS / "check_guard_scan_surface.py"
)
meta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(meta)  # type: ignore[union-attr]

_REGISTER_CALL = re.compile(r"register_grep_guard\s*\(")


def _grep_guard_callers_ground_truth() -> set[str]:
    """独立机械重算：scripts/*.py 里真正调用 register_grep_guard(...) 的模块名。"""
    callers: set[str] = set()
    for path in SCRIPTS.glob("*.py"):
        if path.stem in {"check_guard_scan_surface", "guard_lib"}:
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.lstrip()
            if s.startswith(("#", "from ", "import ")):
                continue
            if _REGISTER_CALL.search(line):
                callers.add(path.stem)
                break
    return callers


def test_self_discovery_matches_ground_truth_not_hardcoded() -> None:
    """GUARDS_UNDER_META 来自机械自发现，等于独立重算的 register_grep_guard 调用方全集。"""
    discovered = set(meta.discover_meta_guards())
    assert discovered == _grep_guard_callers_ground_truth()
    # 名实相符：必须覆盖所有 8 个 register_grep_guard 调用点所在的 4 个模块（含此前漏掉的两个）。
    assert {"check_grep_guards_batch", "check_adapter_write_ban"} <= discovered, (
        "元守卫必须纳入 check_grep_guards_batch / check_adapter_write_ban — "
        "这正是旧硬编码 2-tuple 漏掉的、立设动因所在"
    )
    assert "check_guard_scan_surface" not in discovered  # 元守卫不监管自身
    assert "guard_lib" not in discovered  # 库只定义 register_grep_guard，不是守卫


def test_meta_guard_passes_clean_tree() -> None:
    """干净树上元守卫零漂移（自发现纳入新守卫面后仍绿——含理由豁免）。"""
    assert meta.main() == 0


def test_register_grep_guard_callers_are_all_importable() -> None:
    """自发现的每个模块都能 import（注册在 import 即生效，无副作用）。"""
    import importlib

    for mod in meta.discover_meta_guards():
        importlib.import_module(mod)  # 不抛即合格
