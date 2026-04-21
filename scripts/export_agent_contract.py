#!/usr/bin/env python3
"""
export_agent_contract.py — preflight 段 4

按 agent-contract-enforcement.mdc 强约束：
    Each project must maintain its own scripts/export_agent_contract.py tailored
    to that project's API surface (routes, CLI commands, MCP tools, etc.).

zw-brain 的 4 入口（设计基线 §4.1 + §4.2）：
    L1.1 WebUI         (前端 SPA — 不暴露 API；本脚本不扫)
    L1.2 REST API      (zw_brain/entry/rest/ + OpenAPI spec)
    L1.3 MCP Server    (zw_brain/entry/mcp/tools/*.json)
    L1.4 A2A Server    (zw_brain/entry/a2a/agent_card.json)

本脚本两种模式：
    1. （默认）扫描 4 入口源代码 + 生成 docs/agent_integration.md
    2. --check：扫描 + 对比当前 docs/agent_integration.md，发现 drift 退出 1

设计原则（agent-contract-enforcement.mdc）：
    - Treat docs/agent_integration.md as generated from live code; never edit by hand
    - One canonical path per intent: don't generate multiple endpoints with same outcome
    - Skill ↔ entry 对应关系也要写入文档（基线 D2：4 入口共享 Skill 契约）

Phase 0 早期 zw_brain/ 不存在时：
    - 生成空骨架 docs/agent_integration.md（带 "no entries discovered" 标记）
    - --check 模式：若 doc 不存在 → 创建空骨架；若存在 → 与生成结果对比

接入：scripts/preflight.sh 段 4（实际由 dev-rules 模板调用）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "agent_integration.md"

# 入口 schema 文件位置（基线 §4.4.5 工程布局）
ENTRY_REST = REPO_ROOT / "zw_brain" / "entry" / "rest"
ENTRY_MCP = REPO_ROOT / "zw_brain" / "entry" / "mcp"
ENTRY_A2A = REPO_ROOT / "zw_brain" / "entry" / "a2a"
SKILL_REGISTRY = REPO_ROOT / "zw_brain" / "skill_registration" / "registered"


def discover_rest() -> list[dict[str, Any]]:
    """扫描 OpenAPI spec / FastAPI route decorators / Flask route decorators。

    Phase 0 占位实现：找 zw_brain/entry/rest/openapi.{yaml,json} 或
    zw_brain/entry/rest/routes/*.py，提取 path + method。
    """
    if not ENTRY_REST.exists():
        return []
    routes: list[dict[str, Any]] = []
    # OpenAPI spec
    for spec in ENTRY_REST.glob("openapi.*"):
        try:
            if spec.suffix in (".json",):
                data = json.loads(spec.read_text(encoding="utf-8"))
            else:
                # YAML — 不引入 PyYAML 依赖，跳过解析仅记录存在
                routes.append({"source": str(spec.relative_to(REPO_ROOT)), "note": "YAML spec found (parser not loaded)"})
                continue
            for path, ops in data.get("paths", {}).items():
                for method, op in ops.items():
                    if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                        routes.append({
                            "method": method.upper(),
                            "path": path,
                            "summary": op.get("summary", ""),
                            "operation_id": op.get("operationId", ""),
                            "source": str(spec.relative_to(REPO_ROOT)),
                        })
        except (json.JSONDecodeError, OSError) as e:
            routes.append({"source": str(spec.relative_to(REPO_ROOT)), "error": str(e)})
    return routes


def discover_mcp() -> list[dict[str, Any]]:
    """扫描 MCP tool descriptors（zw_brain/entry/mcp/tools/*.json）。"""
    if not ENTRY_MCP.exists():
        return []
    tools: list[dict[str, Any]] = []
    for spec in (ENTRY_MCP / "tools").glob("*.json") if (ENTRY_MCP / "tools").exists() else []:
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
            tools.append({
                "name": data.get("name", spec.stem),
                "description": data.get("description", ""),
                "input_schema": bool(data.get("inputSchema") or data.get("input_schema")),
                "source": str(spec.relative_to(REPO_ROOT)),
            })
        except (json.JSONDecodeError, OSError) as e:
            tools.append({"name": spec.stem, "error": str(e)})
    return tools


def discover_a2a() -> list[dict[str, Any]]:
    """扫描 A2A agent card（zw_brain/entry/a2a/agent_card.json）。"""
    if not ENTRY_A2A.exists():
        return []
    cards: list[dict[str, Any]] = []
    for spec in ENTRY_A2A.glob("agent_card*.json"):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
            cards.append({
                "name": data.get("name", spec.stem),
                "description": data.get("description", ""),
                "skills_exposed": len(data.get("skills", [])),
                "source": str(spec.relative_to(REPO_ROOT)),
            })
        except (json.JSONDecodeError, OSError) as e:
            cards.append({"name": spec.stem, "error": str(e)})
    return cards


def discover_skills() -> list[dict[str, Any]]:
    """扫描已注册的 Skill manifest（zw_brain/skill_registration/registered/*.json）。"""
    if not SKILL_REGISTRY.exists():
        return []
    skills: list[dict[str, Any]] = []
    for spec in SKILL_REGISTRY.glob("*.json"):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
            skills.append({
                "skill_id": data.get("skill_id", spec.stem),
                "title": data.get("title", ""),
                "version": data.get("version", ""),
                "side_effects": data.get("side_effects", []),
                "source": str(spec.relative_to(REPO_ROOT)),
            })
        except (json.JSONDecodeError, OSError) as e:
            skills.append({"skill_id": spec.stem, "error": str(e)})
    return skills


def render(rest: list, mcp: list, a2a: list, skills: list) -> str:
    """生成 docs/agent_integration.md。"""
    lines = [
        "<!-- AUTO-GENERATED by scripts/export_agent_contract.py — DO NOT EDIT BY HAND -->",
        "<!-- Edit the source code (zw_brain/entry/* + skill_registration/registered/*) instead. -->",
        "",
        "# Agent Integration Contract — zw-brain",
        "",
        "> 由 `scripts/export_agent_contract.py` 从代码扫描生成；",
        "> 修改请编辑 `zw_brain/entry/{rest,mcp,a2a}/` + `zw_brain/skill_registration/registered/`，",
        "> 然后运行 `python scripts/export_agent_contract.py` 重新生成。",
        ">",
        "> 设计基线 D2：4 入口（WebUI / REST / MCP / A2A）共享同一套 Skill 契约。",
        "",
        "## L1.2 REST API",
        "",
    ]
    if rest:
        lines.append("| Method | Path | Summary | Operation ID | Source |")
        lines.append("| ------ | ---- | ------- | ------------ | ------ |")
        for r in rest:
            if "error" in r:
                lines.append(f"| ! | (parse error) | {r.get('error', '')} | | `{r['source']}` |")
            elif "method" not in r:
                lines.append(f"| (note) | | {r.get('note', '')} | | `{r['source']}` |")
            else:
                lines.append(
                    f"| {r['method']} | `{r['path']}` | {r['summary']} | "
                    f"`{r['operation_id']}` | `{r['source']}` |"
                )
    else:
        lines.append("_No REST endpoints discovered (Phase 0 — `zw_brain/entry/rest/` not yet present)._")
    lines.append("")

    lines.append("## L1.3 MCP Server")
    lines.append("")
    if mcp:
        lines.append("| Tool Name | Description | Has Input Schema | Source |")
        lines.append("| --------- | ----------- | ---------------- | ------ |")
        for t in mcp:
            if "error" in t:
                lines.append(f"| {t['name']} | (parse error) {t['error']} | | |")
            else:
                lines.append(f"| `{t['name']}` | {t['description']} | {t['input_schema']} | `{t['source']}` |")
    else:
        lines.append("_No MCP tools discovered (Phase 0 — `zw_brain/entry/mcp/tools/` not yet present)._")
    lines.append("")

    lines.append("## L1.4 A2A Server")
    lines.append("")
    if a2a:
        lines.append("| Agent Card | Description | Skills Exposed | Source |")
        lines.append("| ---------- | ----------- | -------------- | ------ |")
        for c in a2a:
            if "error" in c:
                lines.append(f"| {c['name']} | (parse error) {c['error']} | | |")
            else:
                lines.append(f"| `{c['name']}` | {c['description']} | {c['skills_exposed']} | `{c['source']}` |")
    else:
        lines.append("_No A2A agent cards discovered (Phase 0 — `zw_brain/entry/a2a/` not yet present)._")
    lines.append("")

    lines.append("## Registered Skills (the canonical contract — D2)")
    lines.append("")
    if skills:
        lines.append("| Skill ID | Title | Version | Side Effects | Source |")
        lines.append("| -------- | ----- | ------- | ------------ | ------ |")
        for s in skills:
            if "error" in s:
                lines.append(f"| {s['skill_id']} | (parse error) {s['error']} | | | |")
            else:
                effects = ", ".join(s["side_effects"]) if s["side_effects"] else "(read-only)"
                lines.append(f"| `{s['skill_id']}` | {s['title']} | {s['version']} | {effects} | `{s['source']}` |")
    else:
        lines.append("_No registered Skills discovered (Phase 0 — `zw_brain/skill_registration/registered/` not yet present)._")
    lines.append("")

    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- REST endpoints: {len(rest)}")
    lines.append(f"- MCP tools: {len(mcp)}")
    lines.append(f"- A2A agent cards: {len(a2a)}")
    lines.append(f"- Registered Skills: {len(skills)}")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare generated content with on-disk docs/agent_integration.md; exit 1 on drift")
    args = parser.parse_args()

    rest = discover_rest()
    mcp = discover_mcp()
    a2a = discover_a2a()
    skills = discover_skills()
    new_content = render(rest, mcp, a2a, skills)

    if args.check:
        if not DOC_PATH.exists():
            print(f"[contract] FAIL: {DOC_PATH.relative_to(REPO_ROOT)} does not exist; run without --check to generate")
            return 1
        existing = DOC_PATH.read_text(encoding="utf-8")
        if existing == new_content:
            print(f"[contract] OK: {DOC_PATH.relative_to(REPO_ROOT)} in sync with discovered entries "
                  f"(REST={len(rest)} MCP={len(mcp)} A2A={len(a2a)} Skills={len(skills)})")
            return 0
        print(f"[contract] FAIL: {DOC_PATH.relative_to(REPO_ROOT)} drift detected")
        print("  Run: python scripts/export_agent_contract.py")
        return 1

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(new_content, encoding="utf-8")
    print(f"[contract] generated: {DOC_PATH.relative_to(REPO_ROOT)} "
          f"(REST={len(rest)} MCP={len(mcp)} A2A={len(a2a)} Skills={len(skills)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
