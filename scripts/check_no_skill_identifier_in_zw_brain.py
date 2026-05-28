#!/usr/bin/env python3
"""check_no_skill_identifier_in_zw_brain.py — preflight 段（D33 retrofit）

D33 (2026-05-28) 决策：zw-brain 内部 "skill" 词整体退役 → 统一 "capability"。
但为避免 5 消费面 API surface（webui/api/cli/mcp/a2a）breaking change，envelope
contract 字段 `skill_id` + 关联内部抽象（SkillContext / SkillPipeline / UnknownSkillError
等共 14 个标识符）作为「明确豁免」保留。**新增**包含 `skill` 字符串的 class/def
必须显式注册到下方 ALLOWED_SKILL_IDENTIFIERS 白名单，否则 preflight 红灯。

判定规则：
    - 范围：zw_brain/ 下所有 .py 文件
    - 形式：以 'class ' / 'def ' 开头（含缩进）的行，标识符含 'skill' 子串（大小写不敏感）
    - 白名单：ALLOWED_SKILL_IDENTIFIERS 静态集合（D33 PR 时 baseline 14 个）

退出码：
    0 = 通过（所有 skill 标识符在白名单内）
    1 = 至少一个新增 skill 标识符未在白名单

使用：
    ./scripts/check_no_skill_identifier_in_zw_brain.py

新增 skill 标识符如何处理：
    1. 首选方案：用 capability 命名（CapabilityFoo / handle_capability_bar）
    2. 如果必须保留 skill 词（envelope contract / 历史抽象），把标识符加进 ALLOWED_SKILL_IDENTIFIERS
       并在 commit message / PR 描述里解释 contract surface 理由
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ZW_BRAIN = REPO / "zw_brain"

# D33 baseline：14 个 envelope contract / 内部抽象，保留作为明确豁免（2026-05-28）
# 未来如必须新增 skill 标识符，须在此集合里显式登记 + PR 描述说明 contract 理由
ALLOWED_SKILL_IDENTIFIERS: frozenset[str] = frozenset({
    # entry/rest 层 — envelope contract API handler
    "_handle_api_skill_get",
    "_handle_api_skill_post",
    "_trusted_skill_payload",
    # shared 层 — envelope contract helper
    "get_rest_api_skills_endpoint",
    "build_trusted_skill_payload",
    # command/adapter_routing — envelope-side adapter mapper
    "adapter_operation_from_skill",
    "aggregate_type_from_skill",
    # command/deps — 内部核心抽象，与 BrainService.invoke_skill envelope 一致
    "SkillContext",
    # command/pipeline — 内部核心抽象
    "SkillPipeline",
    # command/brain — envelope contract 主入口（BrainService.invoke_skill）
    "invoke_skill",
    "_build_skill_context",
    "_dispatch_skill",
    "_adapter_operation_from_skill",
    "_aggregate_type_from_skill",
    # domain/errors — envelope error 类型
    "UnknownSkillError",
})

# 匹配 class XxxSkill / def xxx_skill 等 — 标识符含 skill 子串（大小写不敏感）
_IDENT_RE = re.compile(r"^\s*(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _identifier_contains_skill(name: str) -> bool:
    return "skill" in name.lower()


def scan_file(path: Path) -> list[tuple[int, str]]:
    """返回违规 (lineno, identifier) 列表（已排除白名单）。"""
    violations: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = _IDENT_RE.match(line)
        if not match:
            continue
        identifier = match.group(2)
        if not _identifier_contains_skill(identifier):
            continue
        if identifier in ALLOWED_SKILL_IDENTIFIERS:
            continue
        violations.append((lineno, identifier))
    return violations


def main() -> int:
    if not ZW_BRAIN.is_dir():
        print(f"[no-skill-ident] skip: {ZW_BRAIN} not present")
        return 0

    total_files = 0
    total_violations: list[tuple[Path, int, str]] = []
    for path in sorted(ZW_BRAIN.rglob("*.py")):
        total_files += 1
        for lineno, ident in scan_file(path):
            total_violations.append((path, lineno, ident))

    if total_violations:
        print(f"[no-skill-ident] FAIL: scanned {total_files} py files, {len(total_violations)} new skill identifier(s) outside whitelist:")
        for path, lineno, ident in total_violations:
            rel = path.relative_to(REPO)
            print(f"  - {rel}:{lineno}  {ident}")
        print()
        print("[no-skill-ident] hint: D33 (2026-05-28) 决策——新代码用 capability 命名；如必须保留 skill 词")
        print("[no-skill-ident]       (envelope contract / 历史抽象)，把标识符加进 ALLOWED_SKILL_IDENTIFIERS 并在")
        print("[no-skill-ident]       PR 描述里解释 contract surface 理由。")
        return 1

    print(f"[no-skill-ident] ok: scanned {total_files} py files, all skill identifiers in D33 baseline whitelist ({len(ALLOWED_SKILL_IDENTIFIERS)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
