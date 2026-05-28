#!/usr/bin/env python3
"""preflight 段 38 — 三角连接守卫（飞轮齿轮组硬化）.

zw-brain 业务提升飞轮（docs/approved/zw-brain-flywheel.md）的三轴机械连接：
  .testing/*.feature  ←→  .twin/eN/plan.yaml  ←→  tests/*

每个 .feature header 含 3 个三角字段：
  # Owner: e1|e2|e3|e4|e5|e6           — 哪个 worker owns
  # Pytest: <path> 或 pending           — 哪个 pytest 实现
  # Twin-F: eN.FX 或 cross 或 pending   — 哪个 F-item 承接

本脚本三向校验：
  1. Owner 字段是 6 个合法 worker 之一；对应 .twin/{owner}-*/ 目录存在
  2. Pytest 字段除 pending 外，引用的所有 tests/*.py 文件存在
  3. Twin-F 字段除 cross/pending 外，eN.FX 格式合法 + 对应 plan.yaml F-item 存在
  4. 双向反向校验：Twin-F=eN.FX 时，对应 F-item 的 spec_ref 必须包含本 .feature 路径

任意失配 commit 拦下。

退出码：0 = 全部通过；1 = 至少一处违反

使用：
    ./scripts/check_trace_triangle.py
    ./scripts/check_trace_triangle.py --verbose

接入：scripts/preflight.sh 段 38
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
TESTING_DIR = REPO / ".testing"
TWIN_DIR = REPO / ".twin"

VALID_OWNERS = {"e1", "e2", "e3", "e4", "e5", "e6"}
VALID_TWIN_F_SPECIAL = {"cross", "pending"}

OWNER_RE = re.compile(r"^# Owner:\s*(\S+)")
PYTEST_RE = re.compile(r"^# Pytest:\s*(.+)")
TWIN_F_RE = re.compile(r"^# Twin-F:\s*(.+)")
TWIN_F_VALUE_RE = re.compile(r"^e[1-6]\.F\d+$")
PYTEST_PATH_RE = re.compile(r"(tests/[\w/\-\.]+\.py|zw-brain-web/tests/[\w/\-\.]+\.(?:ts|spec\.ts))")
TWIN_F_INSIDE_TEXT_RE = re.compile(r"\be([1-6])\.F(\d+)\b")


def _resolve_worker_dir(owner: str) -> Path | None:
    """Owner=e1 → .twin/e1-*/ 目录路径"""
    for child in TWIN_DIR.iterdir():
        if child.is_dir() and child.name.startswith(f"{owner}-"):
            return child
    return None


def _parse_feature_header(feature_path: Path) -> tuple[str | None, str | None, str | None]:
    """读 feature header 前 30 行，返回 (owner, pytest, twin_f)"""
    owner = pytest_val = twin_f = None
    try:
        with feature_path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i > 30:
                    break
                if m := OWNER_RE.match(line):
                    owner = m.group(1).strip()
                elif m := PYTEST_RE.match(line):
                    pytest_val = m.group(1).strip()
                elif m := TWIN_F_RE.match(line):
                    twin_f = m.group(1).strip()
    except OSError:
        return None, None, None
    return owner, pytest_val, twin_f


def _load_plan(worker_dir: Path) -> dict | None:
    plan_path = worker_dir / "plan.yaml"
    if not plan_path.is_file():
        return None
    try:
        return yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None


def _check_feature(feature_path: Path, plan_cache: dict[str, dict]) -> list[str]:
    """检查一个 .feature 的三角字段；返回违规字符串列表"""
    violations: list[str] = []
    rel = feature_path.relative_to(REPO).as_posix()
    owner, pytest_val, twin_f = _parse_feature_header(feature_path)

    # 字段必填
    if owner is None:
        violations.append(f"{rel}: missing # Owner: header")
    if pytest_val is None:
        violations.append(f"{rel}: missing # Pytest: header")
    if twin_f is None:
        violations.append(f"{rel}: missing # Twin-F: header")

    # Owner 校验
    if owner is not None:
        if owner not in VALID_OWNERS:
            violations.append(
                f"{rel}: Owner='{owner}' not in {sorted(VALID_OWNERS)}"
            )
        else:
            wd = _resolve_worker_dir(owner)
            if wd is None:
                violations.append(
                    f"{rel}: Owner='{owner}' has no matching .twin/{owner}-*/ directory"
                )

    # Pytest 校验
    if pytest_val is not None and pytest_val != "pending":
        for match in PYTEST_PATH_RE.finditer(pytest_val):
            path_str = match.group(1)
            if not (REPO / path_str).is_file():
                violations.append(
                    f"{rel}: Pytest references missing file '{path_str}'"
                )

    # Twin-F 校验
    if twin_f is not None and twin_f not in VALID_TWIN_F_SPECIAL:
        # 可能是 eN.FX 或 "eN.FX + eN.FY"（多个 F-item，组合形态）
        f_items_referenced = TWIN_F_INSIDE_TEXT_RE.findall(twin_f)
        if not f_items_referenced:
            violations.append(
                f"{rel}: Twin-F='{twin_f}' invalid format (expect eN.FX or 'cross' or 'pending')"
            )
        else:
            # 验证每个 eN.FX 都存在
            for worker_n, f_num in f_items_referenced:
                worker_key = f"e{worker_n}"
                f_id = f"F{f_num}"
                # 拿 plan
                if worker_key not in plan_cache:
                    wd = _resolve_worker_dir(worker_key)
                    if wd is None:
                        violations.append(
                            f"{rel}: Twin-F references e{worker_n} but no .twin/{worker_key}-*/ exists"
                        )
                        continue
                    plan = _load_plan(wd)
                    plan_cache[worker_key] = plan or {}
                plan = plan_cache.get(worker_key) or {}
                items = plan.get("items") or []
                item_ids = {item.get("id") for item in items}
                if f_id not in item_ids:
                    violations.append(
                        f"{rel}: Twin-F references {worker_key}.{f_id} but plan.yaml has no such F-item"
                    )
                    continue
                # 双向反向校验：F-item 的 spec_ref 必须包含本 .feature 路径
                target_item = next((it for it in items if it.get("id") == f_id), None)
                if target_item is not None:
                    spec_ref = target_item.get("spec_ref") or []
                    if rel not in spec_ref:
                        violations.append(
                            f"{rel}: Twin-F={worker_key}.{f_id} but plan.yaml F-item spec_ref does NOT include this feature path"
                        )

    return violations


def _check_plan_spec_ref_orphans(plan_cache: dict[str, dict]) -> list[str]:
    """对 plan.yaml 中的 spec_ref 反向校验：每个引用的 .feature 必须存在"""
    violations: list[str] = []
    for worker_key, plan in plan_cache.items():
        wd = _resolve_worker_dir(worker_key)
        if wd is None or not plan:
            continue
        plan_rel = (wd / "plan.yaml").relative_to(REPO).as_posix()
        for item in plan.get("items") or []:
            spec_ref = item.get("spec_ref") or []
            f_id = item.get("id", "?")
            for ref in spec_ref:
                if not (REPO / ref).is_file():
                    violations.append(
                        f"{plan_rel} F-item {f_id}: spec_ref='{ref}' references missing .feature"
                    )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="飞轮三角连接守卫")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not TESTING_DIR.is_dir():
        print("[trace-triangle] skip: .testing/ not present")
        return 0
    if not TWIN_DIR.is_dir():
        print("[trace-triangle] skip: .twin/ not present")
        return 0

    plan_cache: dict[str, dict] = {}
    # 预加载所有 worker plan.yaml（确保 orphan 校验扫到全部）
    for child in TWIN_DIR.iterdir():
        if child.is_dir():
            owner_key = child.name.split("-")[0]
            if owner_key in VALID_OWNERS:
                loaded = _load_plan(child) or {}
                # 同 owner 多 workspace 时（如 e6-f12f13-ops-new 无 plan.yaml），
                # 空 plan 不得覆盖已有完整 plan（e6-platform-m0）。
                if loaded.get("items") or owner_key not in plan_cache:
                    plan_cache[owner_key] = loaded

    all_violations: list[str] = []
    scanned = 0
    for feature_path in TESTING_DIR.rglob("*.feature"):
        scanned += 1
        all_violations.extend(_check_feature(feature_path, plan_cache))

    # 反向校验 plan.yaml spec_ref 引用的 .feature 都存在
    all_violations.extend(_check_plan_spec_ref_orphans(plan_cache))

    if all_violations:
        print(f"[trace-triangle] FAIL: scanned {scanned} .feature(s), {len(all_violations)} violation(s):")
        for v in all_violations:
            print(f"  {v}")
        print()
        print("[trace-triangle] hint: 三角字段（# Owner / # Pytest / # Twin-F + plan.yaml spec_ref）必须双向一致。")
        print("[trace-triangle] 飞轮设计: docs/approved/zw-brain-flywheel.md §四 + 附录 B")
        return 1

    print(f"[trace-triangle] OK: scanned {scanned} .feature(s); all triangle links valid")
    if args.verbose:
        print(f"  (workers cached: {len(plan_cache)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
