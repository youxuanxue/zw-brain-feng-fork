"""Tests for scripts/check_read_path_scan_to_one.py (preflight 段 32c — 详情页 N+1 机械化).

覆盖：next-scan / loop-scan-to-one(return|break) 命中；aggregate(continue) /
视图门面(.view.*.list_all) / brain 有界引用(brain.list_*) / 已豁免 不命中；
以及在真实树上的整体 PASS。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_read_path_scan_to_one.py"

pytestmark = pytest.mark.no_db


def _load_module():
    spec = importlib.util.spec_from_file_location("check_scan_to_one", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _violations(tmp_path: Path, body: str) -> list[str]:
    module = _load_module()
    target = tmp_path / "sample.py"
    target.write_text(body, encoding="utf-8")
    # 把扫描根 + REPO 指向临时树，使相对路径与命中逻辑可独立验证
    module.REPO = tmp_path
    module.SCAN_ROOTS = (tmp_path,)
    return module._check_file(target)


def test_flags_next_scan_over_repo_list(tmp_path: Path) -> None:
    body = (
        "def get(deps, rid):\n"
        "    return next((x for x in deps.repos.application.list_records(tenant_id='t')\n"
        "                 if x.application_code == rid), None)\n"
    )
    viols = _violations(tmp_path, body)
    assert len(viols) == 1 and "next" in viols[0]


def test_flags_loop_scan_to_one_with_return(tmp_path: Path) -> None:
    body = (
        "def get(deps, rid):\n"
        "    for x in deps.repos.delivery.list_tasks(tenant_id='t'):\n"
        "        if x.delivery_code == rid:\n"
        "            return x\n"
    )
    viols = _violations(tmp_path, body)
    assert len(viols) == 1 and "for" in viols[0]


def test_flags_loop_scan_to_one_with_break(tmp_path: Path) -> None:
    body = (
        "def overlay(deps, rid, out):\n"
        "    for x in deps.repos.approval.list_cases(tenant_id='t'):\n"
        "        if x.application_code == rid:\n"
        "            out['hit'] = x\n"
        "            break\n"
    )
    assert len(_violations(tmp_path, body)) == 1


def test_flags_inline_instantiated_repository(tmp_path: Path) -> None:
    """内联实例化 `XRepository().list_*()` 的 scan-to-one 也须命中（recall 不留洞）。"""
    body = (
        "def load(application_id):\n"
        "    from zw_brain.domain.repositories.application import ApplicationRepository\n"
        "    for r in ApplicationRepository().list_records(tenant_id='t'):\n"
        "        if r.application_code == application_id:\n"
        "            return r\n"
    )
    assert len(_violations(tmp_path, body)) == 1


def test_ignores_aggregate_loop_with_continue(tmp_path: Path) -> None:
    """聚合循环（continue 跳过自身后继续收集多条）不是 scan-to-one。"""
    body = (
        "def agg(deps, exclude):\n"
        "    out = []\n"
        "    for r in deps.repos.application.list_records(tenant_id='t'):\n"
        "        if r.application_code == exclude:\n"
        "            continue\n"
        "        out.append(r)\n"
        "    return out\n"
    )
    assert _violations(tmp_path, body) == []


def test_ignores_view_facade_list_all(tmp_path: Path) -> None:
    """视图门面（内存快照、无索引 getter 可替代）不在范围。"""
    body = (
        "def dedup(deps, cid):\n"
        "    return next((x for x in deps.view.requests.list_all()\n"
        "                 if x.get('resourceId') == cid), None)\n"
    )
    assert _violations(tmp_path, body) == []


def test_ignores_brain_bounded_reference(tmp_path: Path) -> None:
    """brain.list_zones() 等有界引用集（非仓储）不在范围。"""
    body = (
        "def get_zone(brain, zid):\n"
        "    for item in brain.list_zones():\n"
        "        if item['id'] == zid:\n"
        "            return item\n"
    )
    assert _violations(tmp_path, body) == []


def test_respects_exemption_marker(tmp_path: Path) -> None:
    body = (
        "def get(deps, rid):\n"
        "    # scan-to-one-ok: 有界引用集，无 get_ 可替代\n"
        "    return next((x for x in deps.repos.capability_package.list_packages()\n"
        "                 if x.package_slug == rid), None)\n"
    )
    assert _violations(tmp_path, body) == []


def test_real_tree_passes() -> None:
    """修复 + 豁免落地后，真实树整体 PASS。"""
    module = _load_module()
    assert module.main() == 0
