#!/usr/bin/env python3
"""旧 xlsx 128 用例 → tests/fixtures/legacy_smoke.yaml 一次性结构化抽取.

zw-brain 飞轮势能源之一（详见 docs/approved/zw-brain-flywheel.md §三.2）：
  - 输入: old/共享平台V5.0.2-冒烟.xlsx（131 数据行；不在 git，本机维护）
  - 输出: tests/fixtures/legacy_smoke.yaml（结构化，进 git，供 pytest parametrize 用）

每条用例字段：
  xlsx_row: int                              # 数据行号（1-based）
  name: str                                  # 用例名（业务方亲笔写的）
  system: str                                # 系统大类
  module: str                                # 模块
  sub_module: str | null                     # 二级模块
  priority: str                              # 最高 | 高 | 中
  case_type: str | null                      # 用例类型（功能 / 兼容性等）
  preconditions: str                         # 前置条件（保留原样多行）
  steps: str                                 # 步骤描述
  expected: str                              # 预期结果
  disposition: enum                          # mapped | not_reproduce | deferred | external
  feature_ref: str | null                    # 对应 .feature 路径（disposition=mapped 时必有）
  rationale: str | null                      # 不复刻 / 延后 / 外部依赖理由（disposition≠mapped 时必有）

disposition 与 feature_ref 通过解析 .testing/cross-cutting/legacy-128-mapping.md 推断。

使用：
    ./scripts/extract_legacy_smoke_xlsx.py                    # 跑一次抽取，覆写 yaml
    ./scripts/extract_legacy_smoke_xlsx.py --dry-run          # 看输出不写文件
    ./scripts/extract_legacy_smoke_xlsx.py --check            # 校验 yaml 与 xlsx 一致（CI 模式，xlsx 缺则 skip）

接入：本脚本不进 preflight 段；输出 yaml 是飞轮势能源的结构化产物，由 PR2 land 一次 + 后续偶发刷新。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

try:
    import openpyxl
except ImportError:
    openpyxl = None  # CI 环境可能没装；--check 模式 skip

import yaml

REPO = Path(__file__).resolve().parent.parent
XLSX_PATH = REPO / "old" / "共享平台V5.0.2-冒烟.xlsx"
MAPPING_DOC = REPO / ".testing" / "cross-cutting" / "legacy-128-mapping.md"
OUTPUT_YAML = REPO / "tests" / "fixtures" / "legacy_smoke.yaml"

DISPOSITION_BY_EMOJI = {
    "✅": "mapped",
    "❌": "not_reproduce",
    "⏸️": "deferred",
    "⏸": "deferred",
    "⚠️": "external",
    "⚠": "external",
}

# mapping doc 表行：| <row> | <用例名> | <优先级> | <处置> | <映射> |
# 处置列含 emoji + 短语
MAPPING_TABLE_ROW_RE = re.compile(
    r"^\|\s*([0-9a-z]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|(?:\s*([^|]*?)\s*\|)?"
)
# mapping doc 中 feature 引用格式："wave-0 j1-application-draft" 或 "wave-1 j1-objection-use"
# 形态：<wave-N> 空格 <feature-name>（无 features/ 或 .feature 后缀）
FEATURE_SHORTHAND_RE = re.compile(r"\bwave-([0-4])\s+([a-z0-9][a-z0-9_\-]+)")

# wave 短号 → 完整目录名（与 .testing/waves/ 下实际目录对齐）
_WAVE_DIR_FULL: dict[str, str] = {
    "0": "wave-0-golden-path",
    "1": "wave-1-j1-j2-closed-loop",
    "2": "wave-2-engines-b1-zones",
    "3": "wave-3-protocol-tenant-national",
    "4": "wave-4-legacy-retirement",
}


def _resolve_feature_path(wave_num: str, feature_name: str) -> str | None:
    """short ('wave-0', 'j1-application-draft') → full path"""
    dir_full = _WAVE_DIR_FULL.get(wave_num)
    if not dir_full:
        return None
    candidate = f".testing/waves/{dir_full}/features/{feature_name}.feature"
    if (REPO / candidate).is_file():
        return candidate
    return None


class LiteralDumper(yaml.SafeDumper):
    """让长字符串走 | literal block 格式"""


def _str_representer(dumper, data):
    if "\n" in data or len(data) > 80:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


LiteralDumper.add_representer(str, _str_representer)


def _parse_mapping_doc(doc_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """解析 mapping doc，返回 (by_row, by_name) 两个索引.

    mapping doc 行号已知漂移（row 17/19/39-44/53/54 等）；优先按"用例名"匹配，
    行号匹配作 fallback（飞轮接受漂移现实，用语义锚点 — Jobs 风格 §三.2）。

    跨 case 合并行（"65 / 70 / 63 / ..."）展开为多条 by_row entry。
    """
    by_row: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    if not doc_path.is_file():
        return by_row, by_name

    last_feature_ref: str | None = None  # "同上" 时继承前一行的 feature_ref
    for line in doc_path.read_text(encoding="utf-8").split("\n"):
        m = MAPPING_TABLE_ROW_RE.match(line)
        if not m:
            continue
        row_cell, name_cell, prio_cell, disp_cell = m.group(1), m.group(2), m.group(3), m.group(4)
        map_cell = m.group(5) or ""

        # 跳过表头分隔行
        if row_cell in ("---", "ID", "id"):
            continue

        # 解析 disposition
        disp = None
        for emoji, kind in DISPOSITION_BY_EMOJI.items():
            if emoji in disp_cell:
                disp = kind
                break
        if disp is None:
            continue  # 无 emoji 行（如表头），跳过

        # rationale = disp_cell 去除 emoji 后的短语
        rationale = disp_cell
        for emoji in DISPOSITION_BY_EMOJI:
            rationale = rationale.replace(emoji, "").strip()
        rationale = rationale.lstrip("（(").rstrip("）)").strip() or None

        # feature_ref 从 map_cell 抽取（短形式 → 完整路径；"同上" 继承前一行）
        feature_ref = None
        if feature_match := FEATURE_SHORTHAND_RE.search(map_cell):
            feature_ref = _resolve_feature_path(feature_match.group(1), feature_match.group(2))
            last_feature_ref = feature_ref
        elif "同上" in map_cell and last_feature_ref:
            feature_ref = last_feature_ref

        entry = {
            "disposition": disp,
            "rationale": rationale if disp != "mapped" else None,
            "feature_ref": feature_ref,
        }

        # 按用例名索引（主路径，避免行号漂移）
        name_key = name_cell.strip()
        if name_key:
            by_name[name_key] = entry

        # 按行号索引（fallback；跨 case 合并行展开）
        rows_in_cell: list[str] = []
        for part in re.split(r"\s*/\s*", row_cell):
            part = part.strip()
            if re.match(r"^\d+[a-z]?$", part):
                rows_in_cell.append(part)
        for r in rows_in_cell:
            by_row[r] = entry

    return by_row, by_name


def _normalize(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _extract_xlsx_rows(xlsx_path: Path) -> list[dict[str, Any]]:
    """读 xlsx 第一个 sheet（共享冒烟测试用例），返回 row 字典列表"""
    if openpyxl is None:
        raise RuntimeError("openpyxl not installed")
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["共享冒烟测试用例"]
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
        if not row or all(v is None for v in row):
            continue
        # 列序：ID, 系统, 模块, 二级模块, 用例名, 优先级, 用例类型, 前置, 步骤, 预期, 备注
        if len(row) < 10:
            continue
        sys_, mod, submod, name, prio, ctype, pre, steps, exp = (
            _normalize(row[1]),
            _normalize(row[2]),
            _normalize(row[3]),
            _normalize(row[4]),
            _normalize(row[5]),
            _normalize(row[6]),
            _normalize(row[7]),
            _normalize(row[8]),
            _normalize(row[9]),
        )
        if not name:
            continue
        out.append(
            {
                "xlsx_row": idx,
                "name": name,
                "system": sys_,
                "module": mod,
                "sub_module": submod,
                "priority": prio,
                "case_type": ctype,
                "preconditions": pre,
                "steps": steps,
                "expected": exp,
            }
        )
    return out


def _build_yaml_entries(
    xlsx_rows: list[dict[str, Any]],
    by_row: dict[str, dict],
    by_name: dict[str, dict],
) -> list[dict]:
    """合并 xlsx + mapping → 输出 yaml 条目（保持字段顺序）.

    匹配优先级（飞轮 §三.2 用例名锚点）：
      1. 按 xlsx 用例名匹配 mapping doc 用例名（容忍行号漂移）
      2. fallback: 按 xlsx 数据行号匹配 mapping doc 行号列
    """
    entries: list[dict] = []
    for r in xlsx_rows:
        meta = by_name.get(r["name"]) or by_row.get(str(r["xlsx_row"])) or {}
        ordered = OrderedDict()
        ordered["xlsx_row"] = r["xlsx_row"]
        ordered["name"] = r["name"]
        ordered["system"] = r["system"]
        ordered["module"] = r["module"]
        ordered["sub_module"] = r["sub_module"]
        ordered["priority"] = r["priority"]
        ordered["case_type"] = r["case_type"]
        ordered["preconditions"] = r["preconditions"]
        ordered["steps"] = r["steps"]
        ordered["expected"] = r["expected"]
        ordered["disposition"] = meta.get("disposition") or "unmapped"
        ordered["feature_ref"] = meta.get("feature_ref")
        ordered["rationale"] = meta.get("rationale")
        entries.append(dict(ordered))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="旧 xlsx 128 用例结构化抽取")
    parser.add_argument("--dry-run", action="store_true", help="不写文件，stdout dump 前 3 条")
    parser.add_argument("--check", action="store_true", help="校验已存在 yaml 与 xlsx 一致")
    args = parser.parse_args()

    if not XLSX_PATH.is_file():
        if args.check:
            print(f"[extract-legacy-smoke] skip: {XLSX_PATH.relative_to(REPO)} not present (CI / fresh checkout)")
            return 0
        print(f"[extract-legacy-smoke] FAIL: {XLSX_PATH.relative_to(REPO)} not found")
        return 1

    if openpyxl is None:
        if args.check:
            print("[extract-legacy-smoke] skip: openpyxl not installed (CI / fresh env)")
            return 0
        print("[extract-legacy-smoke] FAIL: openpyxl not installed (uv add openpyxl)")
        return 1

    try:
        xlsx_rows = _extract_xlsx_rows(XLSX_PATH)
    except Exception as exc:
        print(f"[extract-legacy-smoke] FAIL: xlsx parse error: {exc}")
        return 1

    by_row, by_name = _parse_mapping_doc(MAPPING_DOC)
    entries = _build_yaml_entries(xlsx_rows, by_row, by_name)

    header = (
        "# 旧平台 V5.0.2 冒烟用例结构化输出\n"
        "# 自动生成：scripts/extract_legacy_smoke_xlsx.py\n"
        "# 源：old/共享平台V5.0.2-冒烟.xlsx + .testing/cross-cutting/legacy-128-mapping.md\n"
        "# 飞轮势能源：docs/approved/zw-brain-flywheel.md §三.2\n"
        "# 不要手编辑——重跑脚本刷新\n"
    )

    payload = yaml.dump(entries, Dumper=LiteralDumper, allow_unicode=True, sort_keys=False, width=120)
    full = header + "\n" + payload

    if args.dry_run:
        print(full[:1500] + "\n...(truncated)")
        return 0

    if args.check:
        if not OUTPUT_YAML.is_file():
            print(f"[extract-legacy-smoke] FAIL: {OUTPUT_YAML.relative_to(REPO)} missing — 跑非 --check 模式生成")
            return 1
        current = OUTPUT_YAML.read_text(encoding="utf-8")
        if current.strip() != full.strip():
            print(
                f"[extract-legacy-smoke] FAIL: {OUTPUT_YAML.relative_to(REPO)} drift from xlsx; "
                "重跑 scripts/extract_legacy_smoke_xlsx.py 刷新"
            )
            return 1
        print(f"[extract-legacy-smoke] OK: {len(entries)} entries; yaml in sync with xlsx")
        return 0

    OUTPUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_YAML.write_text(full, encoding="utf-8")
    disp_counts: dict[str, int] = {}
    for e in entries:
        disp_counts[e["disposition"]] = disp_counts.get(e["disposition"], 0) + 1
    print(f"[extract-legacy-smoke] OK: wrote {len(entries)} entries to {OUTPUT_YAML.relative_to(REPO)}")
    print(f"  disposition: {disp_counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
