#!/usr/bin/env python3
"""
export_agent_contract.py — preflight 段 4

zw-brain 的 canonical source 是 `zw_brain/skill_registration/registered/*.json`。
本脚本负责：
    1. 从 live code / canonical skill contract 生成 docs/agent_integration.md
    2. 从同一 skill contract 生成 REST OpenAPI projection
    3. 从同一 skill contract 生成 MCP tool descriptors
    4. 从同一 skill contract 生成 A2A agent_card 与 runtime_bindings
    5. --check 时校验上述产物无 drift
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zw_brain.shared.runtime_config import get_rest_api_skills_endpoint
from zw_brain.skill_registration.runtime import is_surface_enabled, validate_manifest

DOC_PATH = REPO_ROOT / "docs" / "agent_integration.md"

ENTRY_REST = REPO_ROOT / "zw_brain" / "entry" / "rest"
ENTRY_MCP = REPO_ROOT / "zw_brain" / "entry" / "mcp"
ENTRY_CLI = REPO_ROOT / "zw_brain" / "entry" / "cli"
ENTRY_A2A = REPO_ROOT / "zw_brain" / "entry" / "a2a"
SKILL_REGISTRY = REPO_ROOT / "zw_brain" / "skill_registration" / "registered"

OPENAPI_PATH = ENTRY_REST / "openapi.json"
MCP_TOOLS_DIR = ENTRY_MCP / "tools"
A2A_CARD_PATH = ENTRY_A2A / "agent_card.json"
A2A_RUNTIME_BINDINGS_PATH = ENTRY_A2A / "tools" / "runtime_bindings.json"
# F4 新增 2 个投影目标（前 3 个 REST/MCP/A2A 已就位）：
#   - WebUI 页面注册（TS 形式，被 src/router/index.ts 旁路读取）
#   - CLI 命令树（JSON，F5 worker 拿来生成 cli/main.py 子命令注册）
WEBUI_PAGE_REGISTRY_PATH = REPO_ROOT / "zw-brain-web" / "src" / "registry" / "pages.generated.ts"
CLI_COMMANDS_PATH = ENTRY_CLI / "commands.generated.json"

A2A_NAME = "zw-brain"
A2A_DESCRIPTION = "政务大脑 — AI-native re-architecture of the legacy Inspur 一体化大数据平台."
A2A_VERSION = "1.0.0"


def get_a2a_endpoint() -> str:
    return get_rest_api_skills_endpoint()


ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {"type": "string"},
        "detail": {"type": "string"},
        "skill_id": {"type": "string"},
    },
}

IAF_CONFIG_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "configured": {"type": "boolean"},
        "development_iam_bypass_enabled": {"type": "boolean"},
        "development_iam_bypass_user": {
            "type": "object",
            "description": "Synthetic identity returned only when development_iam_bypass_enabled is true.",
            "properties": {
                "subject": {"type": "string"},
                "username": {"type": "string"},
                "display_name": {"type": "string"},
                "tenant_id": {"type": "string"},
                "org_code": {"type": "string"},
                "role_codes": {"type": "array", "items": {"type": "string"}},
            },
        },
        "iaf": {"type": "object"},
        "detail": {"type": "string"},
    },
    "required": ["configured", "development_iam_bypass_enabled"],
}



def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_schema(schema: Any) -> dict[str, Any]:
    if isinstance(schema, dict) and schema:
        return schema
    return {"type": "object", "properties": {}}


def sort_skills_for_projection(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(skills, key=lambda item: (bool(item.get("side_effects")), item.get("skill_id", "")))


def is_live(skill: dict[str, Any]) -> bool:
    scope = skill.get("product_scope") or {}
    return scope.get("status") == "live"


def discover_cli() -> list[dict[str, Any]]:
    if not ENTRY_CLI.exists():
        return []
    main_path = ENTRY_CLI / "main.py"
    if not main_path.exists():
        return []
    return [
        {
            "command": "zw-brain-cli <skill_id> --payload '<json>'",
            "source": str(main_path.relative_to(REPO_ROOT)),
        }
    ]


def discover_skills() -> list[dict[str, Any]]:
    if not SKILL_REGISTRY.exists():
        return []
    skills: list[dict[str, Any]] = []
    for spec in sorted(SKILL_REGISTRY.glob("*.json")):
        try:
            data = load_json(spec)
            validate_manifest(data)
            side_effects = list(data.get("side_effects", []))
            skills.append(
                {
                    "skill_id": data.get("skill_id", spec.stem),
                    "title": data.get("title", ""),
                    "description": data.get("description", ""),
                    "version": data.get("version", ""),
                    "input_schema": normalize_schema(data.get("input_schema", {})),
                    "output_schema": normalize_schema(data.get("output_schema", {})),
                    "side_effects": side_effects,
                    "human_confirmation_required": bool(data.get("human_confirmation_required", bool(side_effects))),
                    "audit_required": bool(data.get("audit_required", False)),
                    "audit_class": data.get("audit_class", ""),
                    "permissions": data.get("permissions", []),
                    "auth_policy": data.get("auth_policy", ""),
                    "tenant_scope": data.get("tenant_scope", ""),
                    "registry_source": data.get("registry_source", ""),
                    "compatibility": data.get("compatibility", []),
                    "execution_binding": data.get("execution_binding", ""),
                    "runtime_binding": data.get("runtime_binding", {}),
                    "product_scope": data.get("product_scope", {}),
                    "source": str(spec.relative_to(REPO_ROOT)),
                }
            )
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            skills.append({"skill_id": spec.stem, "error": str(exc), "source": str(spec.relative_to(REPO_ROOT))})
    return skills


def build_query_parameters(input_schema: dict[str, Any]) -> list[dict[str, Any]]:
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    required = set(input_schema.get("required", [])) if isinstance(input_schema, dict) else set()
    parameters: list[dict[str, Any]] = []
    for name in sorted(properties):
        schema = properties[name] if isinstance(properties[name], dict) else {"type": "string"}
        parameter = {
            "name": name,
            "in": "query",
            "required": name in required,
            "schema": schema,
        }
        if schema.get("description"):
            parameter["description"] = schema["description"]
        parameters.append(parameter)
    return parameters


def build_standard_responses(output_schema: dict[str, Any], *, write: bool, protected: bool) -> dict[str, Any]:
    responses = {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": output_schema,
                }
            },
        },
        "400": {
            "description": "Brain service validation error",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        "404": {
            "description": "Unknown skill id, skill surface disabled, or HTTP route not found",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        "422": {
            "description": "Referenced domain entity missing (error=entity_not_found); distinct from route/skill 404",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    }
    if protected:
        responses["403"] = {
            "description": "Access denied by role / tenant / permission policy",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        }
    if write:
        responses["409"] = {
            "description": "Confirmation required or invalid state",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        }
    responses["401"] = {"description": "Missing/invalid session cookie or Bearer token, or token expired"}
    responses["403"] = {"description": "Forbidden (e.g. csrf_token_invalid on cookie-authenticated writes)"}
    responses["503"] = {"description": "IAF token validation service unavailable"}
    return responses


def build_rest_operation(skill: dict[str, Any], *, method: str) -> dict[str, Any]:
    write = bool(skill.get("side_effects"))
    operation = {
        "summary": skill.get("title", ""),
        "description": skill.get("description", ""),
        "operationId": f"{method.lower()}_{skill['skill_id'].replace('.', '_')}",
        "tags": ["Capability Projection"],
        "x-zwbrain-skill-id": skill["skill_id"],
        "x-zwbrain-side-effects": skill.get("side_effects", []),
        "x-zwbrain-human-confirmation-required": bool(skill.get("human_confirmation_required", False)),
        "x-zwbrain-audit-class": skill.get("audit_class", ""),
        "x-zwbrain-surfaces": skill.get("compatibility", []),
        "x-zwbrain-permissions": skill.get("permissions", []),
        "x-zwbrain-auth-policy": skill.get("auth_policy", ""),
        "x-zwbrain-tenant-scope": skill.get("tenant_scope", ""),
        "responses": build_standard_responses(
            skill.get("output_schema", {}),
            write=write,
            protected=bool(skill.get("permissions")) or bool(skill.get("auth_policy")) or bool(skill.get("tenant_scope")),
        ),
    }
    if method == "GET":
        operation["parameters"] = build_query_parameters(skill.get("input_schema", {}))
    else:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": skill.get("input_schema", {}),
                }
            },
        }
    # Two acceptable auth surfaces: BFF session cookie (with X-CSRF-Token on writes) or Bearer JWT.
    if write:
        operation["security"] = [{"cookieAuth": [], "csrfToken": []}, {"BearerAuth": []}]
    else:
        operation["security"] = [{"cookieAuth": []}, {"BearerAuth": []}]
    return operation


SESSION_PUBLIC_PAYLOAD_SCHEMA = {
    "type": "object",
    "required": ["authenticated", "csrf_token", "expires_at"],
    "properties": {
        "authenticated": {"type": "boolean"},
        "csrf_token": {"type": "string", "description": "Double-submit token; required as X-CSRF-Token on writes"},
        "expires_at": {"type": "integer", "description": "Unix seconds when the access window expires"},
        "actor_snapshot": {"type": "object"},
        "audit_id": {"type": "string"},
        "development_iam_bypass": {"type": "boolean"},
    },
}


def build_iaf_auth_paths() -> dict[str, Any]:
    return {
        "/auth/iaf/config": {
            "get": {
                "summary": "Get IAF IAM public config",
                "operationId": "getIafConfig",
                "responses": {
                    "200": {
                        "description": "IAF public configuration",
                        "content": {"application/json": {"schema": IAF_CONFIG_RESPONSE_SCHEMA}},
                    }
                },
            }
        },
        "/auth/iaf/login": {
            "get": {
                "summary": "Create IAF authorization URL",
                "operationId": "startIafLogin",
                "parameters": [
                    {"name": "redirect_uri", "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "format", "in": "query", "required": False, "schema": {"type": "string", "enum": ["json"]}},
                ],
                "responses": {
                    "200": {"description": "Authorization URL JSON envelope"},
                    "302": {"description": "Redirect to IAM authorization endpoint"},
                    "400": {"description": "Invalid redirect URI"},
                },
            }
        },
        "/auth/iaf/token": {
            "post": {
                "summary": "Exchange IAF authorization code, establish BFF session cookie",
                "description": "On success the server stores access / refresh / id tokens server-side and binds them to an HttpOnly session cookie. The response body intentionally omits all tokens; the client only needs the csrf_token for subsequent writes.",
                "operationId": "exchangeIafCodeForToken",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["code", "state"],
                                "properties": {"code": {"type": "string"}, "state": {"type": "string"}},
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Session established; Set-Cookie carries zw_brain_session (HttpOnly, SameSite=Lax, Secure under HTTPS)",
                        "headers": {
                            "Set-Cookie": {
                                "description": "zw_brain_session=<id>; Path=/; Max-Age=...; HttpOnly; SameSite=Lax; Secure when HTTPS",
                                "schema": {"type": "string"},
                            }
                        },
                        "content": {"application/json": {"schema": SESSION_PUBLIC_PAYLOAD_SCHEMA}},
                    },
                    "400": {"description": "State or code exchange failed"},
                    "401": {"description": "Token verification failed"},
                },
            }
        },
        "/auth/iaf/session": {
            "get": {
                "summary": "Return the public payload for the current BFF session (no side effects)",
                "description": "Lets a freshly opened tab discover its csrf_token without re-running the OAuth flow. The session cookie carries authentication; this endpoint never creates a session.",
                "operationId": "getIafSession",
                "security": [{"cookieAuth": []}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": SESSION_PUBLIC_PAYLOAD_SCHEMA}}, "description": "Current session public payload"},
                    "401": {"description": "No session cookie or session expired"},
                },
            }
        },
        "/auth/iaf/refresh": {
            "post": {
                "summary": "Refresh IAF tokens using the cookie-bound session",
                "description": "Reads the refresh_token from the server-side session; the request body is intentionally ignored. Requires X-CSRF-Token to defeat CSRF.",
                "operationId": "refreshIafToken",
                "security": [{"cookieAuth": [], "csrfToken": []}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": SESSION_PUBLIC_PAYLOAD_SCHEMA}}, "description": "Refreshed session public payload"},
                    "401": {"description": "Session missing or refresh token invalid / expired"},
                    "403": {"description": "csrf_token_invalid"},
                },
            }
        },
        "/auth/iaf/dev-bypass-login": {
            "post": {
                "summary": "Establish a BFF session in development IAM bypass mode",
                "description": "Returns 404 unless both ZW_BRAIN_DEV_IAM_BYPASS=1 and ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only are set. Production servers expose this as a 404.",
                "operationId": "devBypassLogin",
                "responses": {
                    "200": {
                        "description": "Bypass session established",
                        "headers": {"Set-Cookie": {"schema": {"type": "string"}}},
                        "content": {"application/json": {"schema": SESSION_PUBLIC_PAYLOAD_SCHEMA}},
                    },
                    "404": {"description": "Bypass disabled (production-equivalent)"},
                },
            }
        },
        "/auth/iaf/logout": {
            "get": {
                "summary": "Drop the BFF session and build the IAF logout URL",
                "description": "Reads id_token_hint from the cookie-bound session. Clears the session cookie on the response.",
                "operationId": "logoutIaf",
                "security": [{"cookieAuth": []}],
                "parameters": [
                    {"name": "redirect_uri", "in": "query", "required": False, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "IAF logout URL; cookie cleared",
                        "headers": {"Set-Cookie": {"schema": {"type": "string"}}},
                    },
                    "400": {"description": "Invalid redirect URI"},
                },
            }
        },
    }



def build_rest_openapi(skills: list[dict[str, Any]]) -> dict[str, Any]:
    valid_skills = [
        skill
        for skill in skills
        if "error" not in skill and is_surface_enabled(skill, "api") and is_live(skill)
    ]
    paths: dict[str, Any] = {
        "/health": {
            "get": {
                "summary": "Health check",
                "operationId": "healthCheck",
                "responses": {
                    "200": {
                        "description": "Service health",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string"},
                                        "service": {"type": "string"},
                                    },
                                    "required": ["status", "service"],
                                }
                            }
                        },
                    }
                },
            }
        },
        "/openapi.json": {
            "get": {
                "summary": "Get generated OpenAPI spec",
                "operationId": "getOpenAPISpec",
                "responses": {
                    "200": {
                        "description": "Generated OpenAPI document",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    }
                },
            }
        },
        "/api/snapshot": {
            "get": {
                "summary": "Get system snapshot",
                "operationId": "getSystemSnapshot",
                "x-zwbrain-skill-id": "system.snapshot",
                "responses": {
                    "200": {
                        "description": "Snapshot response",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    "401": {"description": "Missing/invalid session cookie or Bearer token"},
                    "503": {"description": "IAF token validation service unavailable"},
                },
                "parameters": [
                    {
                        "name": "role",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["ROLE_SYSTEM", "ROLE_BUSIAUDIT", "ROLE_ORGAN_MANAGER", "ROLE_ORGAN_OPERATER", "ROLE_SECURITY_ADMIN", "ROLE_SECURITY_AUDIT"]},
                        "description": "Web UI role; snapshot lists are redacted server-side to match page access.",
                    }
                ],
                "security": [{"cookieAuth": []}, {"BearerAuth": []}],
            }
        },
    }

    for skill in sort_skills_for_projection(valid_skills):
        if skill["skill_id"] == "system.snapshot":
            continue
        path = f"/api/skills/{skill['skill_id']}"
        if skill.get("side_effects"):
            paths[path] = {"post": build_rest_operation(skill, method="POST")}
        else:
            paths[path] = {"get": build_rest_operation(skill, method="GET")}

    paths.update(build_iaf_auth_paths())

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "zw-brain REST API",
            "version": "1.0.0",
        },
        "paths": paths,
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "cookieAuth": {"type": "apiKey", "in": "cookie", "name": "zw_brain_session"},
                "csrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            }
        },
    }


def rest_entries_from_openapi(openapi: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(openapi.get("paths", {})):
        operations = openapi["paths"][path]
        for method in sorted(operations):
            operation = operations[method]
            entries.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": operation.get("summary", ""),
                    "operation_id": operation.get("operationId", ""),
                    "source": str(OPENAPI_PATH.relative_to(REPO_ROOT)),
                }
            )
    return entries


def build_mcp_tool_descriptor(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": skill["skill_id"],
        "description": skill.get("description") or skill.get("title", ""),
        "inputSchema": skill.get("input_schema", {}),
        "annotations": {
            "mode": "write" if skill.get("side_effects") else "read",
            "humanConfirmationRequired": bool(skill.get("human_confirmation_required", False)),
            "readOnlyHint": not bool(skill.get("side_effects")),
        },
        "x-zwbrain-side-effects": skill.get("side_effects", []),
        "x-zwbrain-audit-class": skill.get("audit_class", ""),
        "x-zwbrain-surfaces": skill.get("compatibility", []),
        "x-zwbrain-permissions": skill.get("permissions", []),
        "x-zwbrain-auth-policy": skill.get("auth_policy", ""),
        "x-zwbrain-tenant-scope": skill.get("tenant_scope", ""),
    }


def build_a2a_card(skills: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sort_skills_for_projection([skill for skill in skills if is_live(skill)])
    return {
        "name": A2A_NAME,
        "description": A2A_DESCRIPTION,
        "version": A2A_VERSION,
        "endpoint": get_a2a_endpoint(),
        "capabilities": {
            "streaming": False,
            "tool_use": True,
        },
        "skills": [
            {
                "id": skill["skill_id"],
                "mode": "write" if skill.get("side_effects") else "read",
                "humanConfirmationRequired": bool(skill.get("human_confirmation_required", False)),
                "auditClass": skill.get("audit_class", ""),
                "surfaces": skill.get("compatibility", []),
                "sideEffects": skill.get("side_effects", []),
            }
            for skill in ordered
        ],
    }


# F4: 8 页面 slug prefix → product anchor 映射；用 skill_id 的点号前缀派生。
# Risk flag：contract_manifest 当前无 ui_page_anchor 字段（D19 决策 GATE-1 已 freeze
# 哲学/数据模型层，技术选型留 Phase 0 PoC）。本派生属于 fallback；如果业务进一步分化页面
# 边界（e.g. P2 vs P3 vs P7 出现新的 catalog.* 用法），需要回 contract_manifest 加显式字段。
WEBUI_PAGE_PREFIX_MAP: list[tuple[str, str]] = [
    # 顺序敏感：先长前缀，再短前缀，避免误归属。
    # 8 页面归属来自 §5.2 + 业务方反馈，未覆盖的进 UNMAPPED_WEBUI_SKILLS（F5/F7 时复查）。
    ("workbench.", "P1"),
    ("data.search", "P2"),
    ("catalog.share_zone.", "P7"),
    ("zone.", "P7"),
    ("topic.", "P7"),
    ("subscription.", "P7"),
    ("catalog.", "P2"),
    ("metadata.", "P2"),
    ("application.", "P3"),
    ("approval.", "P3"),
    ("request.", "P3"),
    ("backflow.", "P3"),
    ("require.", "P3"),
    ("summary.", "P3"),
    ("supplement.", "P3"),
    ("delivery.", "P4"),
    ("credential.", "P4"),
    ("direct_access.", "P4"),
    ("provider.", "P5"),
    ("resource.", "P5"),
    ("service.", "P5"),
    ("governance.", "B1.1"),
    ("audit.", "B1.1"),
    ("compliance.", "B1.1"),
    ("objection.", "B1.1"),
    ("ops.", "B1.1"),
    ("risk.", "B1.1"),
    ("security.", "B1.1"),
    ("capability.", "B1.2"),
    ("external.", "B1.2"),
    ("standard.", "B1.2"),
    ("adapter.", "B1.2"),
    ("legacy.", "B1.2"),
    ("policy.", "B1.2"),
    ("actor.", "B1.2"),
    ("package.", "B1.2"),
    ("tenant.", "B1.2"),
    ("registry.", "B1.2"),
    ("org.", "B1.2"),
    ("system.", "P1"),
]


def derive_webui_anchor(skill_id: str) -> str | None:
    for prefix, anchor in WEBUI_PAGE_PREFIX_MAP:
        if skill_id.startswith(prefix):
            return anchor
    return None


def build_webui_page_registry(skills: list[dict[str, Any]]) -> str:
    """Generate src/registry/pages.generated.ts —— 把 200 skill 按 page anchor 归类。

    每个 P*/B*.vue 关联的 capabilities + roles（input_schema.role.enum）+ 写态。
    """
    webui_skills = [
        skill for skill in skills
        if is_surface_enabled(skill, "webui") and is_live(skill)
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    unmapped: list[str] = []
    for skill in sort_skills_for_projection(webui_skills):
        anchor = derive_webui_anchor(skill["skill_id"])
        if anchor is None:
            unmapped.append(skill["skill_id"])
            continue
        roles = (
            skill.get("input_schema", {})
            .get("properties", {})
            .get("role", {})
            .get("enum", [])
        )
        grouped.setdefault(anchor, []).append({
            "skillId": skill["skill_id"],
            "mode": "write" if skill.get("side_effects") else "read",
            "auditClass": skill.get("audit_class", ""),
            "humanConfirmationRequired": bool(skill.get("human_confirmation_required", False)),
            "roles": list(roles) if isinstance(roles, list) else [],
            "permissions": skill.get("permissions", []),
        })

    # 输出固定 8 + 辅助页 ordering，让 diff 稳定。
    ordered_anchors = ["P1", "P2", "P3", "P4", "P5", "P7", "B1.1", "B1.2"]
    out_lines = [
        "/* AUTO-GENERATED by scripts/export_agent_contract.py — DO NOT EDIT BY HAND.",
        " * Regenerate via: python3 scripts/export_agent_contract.py",
        " * Source of truth: zw_brain/skill_registration/registered/*.json",
        " * 派生规则：skill_id 点号前缀 → WEBUI_PAGE_PREFIX_MAP（脚本内）。",
        " */",
        "",
        "export interface PageCapabilityEntry {",
        "  skillId: string;",
        "  mode: 'read' | 'write';",
        "  auditClass: string;",
        "  humanConfirmationRequired: boolean;",
        "  roles: string[];",
        "  permissions: string[];",
        "}",
        "",
        "export interface PageRegistryEntry {",
        "  anchor: string;",
        "  capabilities: PageCapabilityEntry[];",
        "}",
        "",
        "export const PAGE_REGISTRY: PageRegistryEntry[] = [",
    ]
    for anchor in ordered_anchors:
        entries = grouped.get(anchor, [])
        out_lines.append(f"  {{ anchor: {json.dumps(anchor)}, capabilities: [")
        for entry in entries:
            out_lines.append("    " + json.dumps(entry, ensure_ascii=False) + ",")
        out_lines.append("  ] },")
    out_lines.append("];")
    out_lines.append("")
    out_lines.append(f"export const UNMAPPED_WEBUI_SKILLS: string[] = {json.dumps(sorted(unmapped))};")
    out_lines.append("")
    return "\n".join(out_lines)


def build_cli_commands(skills: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate commands.generated.json —— F5 CLI worker 直接消费这份命令清单。

    每个 live + cli surface 的 skill 派生一条命令：
      command: zw-brain-cli <skill_id>
      args: input_schema.required + optional properties
    """
    cli_skills = sort_skills_for_projection([
        skill for skill in skills
        if is_surface_enabled(skill, "cli") and is_live(skill)
    ])
    commands: list[dict[str, Any]] = []
    for skill in cli_skills:
        input_schema = skill.get("input_schema", {})
        props = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        required = set(input_schema.get("required", []) or [])
        args: list[dict[str, Any]] = []
        for name in sorted(props.keys()):
            field = props[name] or {}
            args.append({
                "name": name,
                "required": name in required,
                "type": field.get("type", "string") if isinstance(field, dict) else "string",
            })
        commands.append({
            "skill_id": skill["skill_id"],
            "title": skill.get("title", ""),
            "description": skill.get("description") or skill.get("title", ""),
            "mode": "write" if skill.get("side_effects") else "read",
            "human_confirmation_required": bool(skill.get("human_confirmation_required", False)),
            "audit_required": bool(skill.get("audit_required", False)),
            "args": args,
        })
    return {
        "_generated_by": "scripts/export_agent_contract.py — DO NOT EDIT BY HAND. "
                         "Regenerate via: python3 scripts/export_agent_contract.py",
        "schema_version": 1,
        "invoke_pattern": "zw-brain-cli <skill_id> --payload '<json>'",
        "endpoint": get_a2a_endpoint(),
        "commands": commands,
    }


def build_runtime_bindings(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for skill in sort_skills_for_projection([skill for skill in skills if is_live(skill)]):
        bindings.append(
            {
                "tool_name": skill["skill_id"],
                "description": skill.get("description") or skill.get("title", ""),
                "protocol_type": "builtin_skill",
                "endpoint": f"{get_a2a_endpoint()}/{skill['skill_id']}",
                "parameters_schema": skill.get("input_schema", {}),
                "config_json": {
                    "mode": "write" if skill.get("side_effects") else "read",
                    "side_effects": skill.get("side_effects", []),
                    "human_confirmation_required": bool(skill.get("human_confirmation_required", False)),
                    "audit_required": bool(skill.get("audit_required", False)),
                    "audit_class": skill.get("audit_class", ""),
                    "surfaces": skill.get("compatibility", []),
                    "permissions": skill.get("permissions", []),
                    "auth_policy": skill.get("auth_policy", ""),
                    "tenant_scope": skill.get("tenant_scope", ""),
                    "registry_source": skill.get("registry_source", ""),
                },
                "version": skill.get("version", ""),
                "invocation_mode": "sync",
                "auth_strategy": "human_confirmation" if skill.get("side_effects") else "none",
            }
        )
    return bindings


def expected_projection_files(
    skills: list[dict[str, Any]],
) -> tuple[dict[Path, str], set[Path], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    valid_skills = [skill for skill in skills if "error" not in skill]
    files: dict[Path, str] = {}

    openapi = build_rest_openapi(valid_skills)
    files[OPENAPI_PATH] = dump_json(openapi)
    rest_entries = rest_entries_from_openapi(openapi)

    mcp_skills = [skill for skill in valid_skills if is_surface_enabled(skill, "mcp") and is_live(skill)]
    mcp_entries: list[dict[str, Any]] = []
    expected_mcp_paths: set[Path] = set()
    for skill in sort_skills_for_projection(mcp_skills):
        path = MCP_TOOLS_DIR / f"{skill['skill_id']}.json"
        expected_mcp_paths.add(path)
        files[path] = dump_json(build_mcp_tool_descriptor(skill))
        mcp_entries.append(
            {
                "name": skill["skill_id"],
                "description": skill.get("description") or skill.get("title", ""),
                "mode": "write" if skill.get("side_effects") else "read",
                "human_confirmation_required": bool(skill.get("human_confirmation_required", False)),
                "input_schema": bool(skill.get("input_schema")),
                "source": str(path.relative_to(REPO_ROOT)),
            }
        )

    a2a_skills = [skill for skill in valid_skills if is_surface_enabled(skill, "a2a") and is_live(skill)]
    card = build_a2a_card(a2a_skills)
    files[A2A_CARD_PATH] = dump_json(card)
    files[A2A_RUNTIME_BINDINGS_PATH] = dump_json(build_runtime_bindings(a2a_skills))
    a2a_entries = [
        {
            "name": card["name"],
            "description": card["description"],
            "skills_exposed": len(card.get("skills", [])),
            "source": str(A2A_CARD_PATH.relative_to(REPO_ROOT)),
        }
    ]

    # F4: 2 个新投影。CLI 命令树 + WebUI 页面注册。
    files[CLI_COMMANDS_PATH] = dump_json(build_cli_commands(valid_skills))
    files[WEBUI_PAGE_REGISTRY_PATH] = build_webui_page_registry(valid_skills)

    return files, expected_mcp_paths, rest_entries, mcp_entries, a2a_entries


def render(
    rest: list[dict[str, Any]],
    cli: list[dict[str, Any]],
    mcp: list[dict[str, Any]],
    a2a: list[dict[str, Any]],
    skills: list[dict[str, Any]],
) -> str:
    lines = [
        "<!-- AUTO-GENERATED by scripts/export_agent_contract.py — DO NOT EDIT BY HAND -->",
        "<!-- Edit the source code (zw_brain/entry/* + skill_registration/registered/*) instead. -->",
        "",
        "# Agent Integration Contract — zw-brain",
        "",
        "> 由 `scripts/export_agent_contract.py` 从代码扫描与 canonical skill contract 生成；",
        "> 修改请编辑 `zw_brain/entry/{rest,cli}/` + `zw_brain/skill_registration/registered/`，",
        "> 然后运行 `python scripts/export_agent_contract.py` 重新生成。",
        ">",
        "> 设计基线 D2：5 消费面（WebUI / REST / CLI / MCP / A2A）共享同一套 Skill 契约。",
        "",
        "## L1.2 REST API",
        "",
    ]
    if rest:
        lines.append("| Method | Path | Summary | Operation ID | Source |")
        lines.append("| ------ | ---- | ------- | ------------ | ------ |")
        for route in rest:
            lines.append(
                f"| {route['method']} | `{route['path']}` | {route['summary']} | `{route['operation_id']}` | `{route['source']}` |"
            )
    else:
        lines.append("_No REST endpoints discovered._")
    lines.append("")

    lines.append("## L1.2.5 CLI")
    lines.append("")
    lines.append(
        "> CLI 采用 generic invoker 模式：1 个统一入口 `zw-brain-cli <skill_id> --payload '<json>'`，"
        "通过 `skill_id` 参数化访问全部 live capability（见 `## L1.5 Skills (Capabilities) Catalog`）。"
        "符合 OPC「单一入口、避免堆 N 个独立子命令」原则。"
    )
    lines.append("")
    if cli:
        lines.append("| Command | Source |")
        lines.append("| ------- | ------ |")
        for command in cli:
            lines.append(f"| `{command['command']}` | `{command['source']}` |")
    else:
        lines.append("_No CLI entries discovered._")
    lines.append("")

    lines.append("## L1.3 MCP Server")
    lines.append("")
    if mcp:
        lines.append("| Tool Name | Mode | Human Confirmation | Description | Has Input Schema | Source |")
        lines.append("| --------- | ---- | ------------------ | ----------- | ---------------- | ------ |")
        for tool in mcp:
            lines.append(
                f"| `{tool['name']}` | {tool['mode']} | {tool['human_confirmation_required']} | {tool['description']} | {tool['input_schema']} | `{tool['source']}` |"
            )
    else:
        lines.append("_No MCP tools discovered._")
    lines.append("")

    lines.append("## L1.4 A2A Server")
    lines.append("")
    if a2a:
        lines.append("| Agent Card | Description | Skills Exposed | Source |")
        lines.append("| ---------- | ----------- | -------------- | ------ |")
        for card in a2a:
            lines.append(f"| `{card['name']}` | {card['description']} | {card['skills_exposed']} | `{card['source']}` |")
    else:
        lines.append("_No A2A agent cards discovered._")
    lines.append("")

    error_skills = [skill for skill in skills if "error" in skill]
    if error_skills:
        lines.append("## ⚠️ Parse Errors")
        lines.append("")
        lines.append("以下 manifest 文件物理存在但解析失败（JSON / 字段校验），不会进入任何 surface 投影。修复后重跑 `python scripts/export_agent_contract.py`。")
        lines.append("")
        lines.append("| Skill ID | Error | Source |")
        lines.append("| -------- | ----- | ------ |")
        for skill in error_skills:
            lines.append(f"| {skill['skill_id']} | {skill['error']} | `{skill['source']}` |")
        lines.append("")

    lines.append("## Registered Skills (the canonical contract — D2)")
    lines.append("")
    lines.append(
        "> 仅列出 `product_scope.status=live` 的能力；`deferred:wave-N` / `external` manifests 物理存在但不投影到 5 surface，"
        "完整边界规则见 [`docs/approved/zw-brain-architecture.md` §6.6](./approved/zw-brain-architecture.md)。"
    )
    lines.append("")
    live_skills = [skill for skill in skills if "error" not in skill and is_live(skill)]
    if live_skills:
        lines.append("| Skill ID | Title | Version | Side Effects | Source |")
        lines.append("| -------- | ----- | ------- | ------------ | ------ |")
        for skill in live_skills:
            effects = ", ".join(skill.get("side_effects", [])) if skill.get("side_effects") else "(read-only)"
            lines.append(f"| `{skill['skill_id']}` | {skill['title']} | {skill['version']} | {effects} | `{skill['source']}` |")
    else:
        lines.append("_No registered Skills discovered._")
    lines.append("")

    live_skill_count = len(live_skills)
    on_disk_count = len(skills)
    error_count = len(error_skills)
    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- REST endpoints: {len(rest)}")
    lines.append(f"- CLI entries: {len(cli)}")
    lines.append(f"- MCP tools: {len(mcp)}")
    lines.append(f"- A2A agent cards: {len(a2a)}")
    if error_count:
        lines.append(
            f"- Registered Skills (live): {live_skill_count} / {on_disk_count} on-disk ({error_count} parse error(s))"
        )
    else:
        lines.append(f"- Registered Skills (live): {live_skill_count} / {on_disk_count} on-disk")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def remove_extra_mcp_files(expected_mcp_paths: set[Path]) -> None:
    if not MCP_TOOLS_DIR.exists():
        return
    for path in MCP_TOOLS_DIR.glob("*.json"):
        if path not in expected_mcp_paths:
            path.unlink()


def check_projection_drift(expected_files: dict[Path, str], expected_mcp_paths: set[Path]) -> list[str]:
    errors: list[str] = []
    for path, expected in expected_files.items():
        if not path.exists():
            errors.append(f"missing generated projection: {path.relative_to(REPO_ROOT)}")
            continue
        current = path.read_text(encoding="utf-8")
        if current != expected:
            errors.append(f"projection drift: {path.relative_to(REPO_ROOT)}")
    if MCP_TOOLS_DIR.exists():
        for path in sorted(MCP_TOOLS_DIR.glob("*.json")):
            if path not in expected_mcp_paths:
                errors.append(f"unexpected MCP tool descriptor: {path.relative_to(REPO_ROOT)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare generated content with on-disk projections and docs; exit 1 on drift",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="explicit regenerate mode (alias of default); useful in tooling for self-documenting intent",
    )
    args = parser.parse_args()
    if args.check and args.update:
        print("[contract] --check and --update are mutually exclusive", file=sys.stderr)
        return 2

    cli = discover_cli()
    skills = discover_skills()
    files, expected_mcp_paths, rest_entries, mcp_entries, a2a_entries = expected_projection_files(skills)
    doc_content = render(rest_entries, cli, mcp_entries, a2a_entries, skills)

    if args.check:
        projection_errors = check_projection_drift(files, expected_mcp_paths)
        if not DOC_PATH.exists():
            projection_errors.append(f"missing generated doc: {DOC_PATH.relative_to(REPO_ROOT)}")
        elif DOC_PATH.read_text(encoding="utf-8") != doc_content:
            projection_errors.append(f"doc drift: {DOC_PATH.relative_to(REPO_ROOT)}")
        if projection_errors:
            print("[contract] FAIL: projection drift detected")
            for error in projection_errors:
                print(f"  - {error}")
            print("  Run: python scripts/export_agent_contract.py")
            return 1
        valid_skill_count = len([skill for skill in skills if "error" not in skill and is_live(skill)])
        print(
            f"[contract] OK: {DOC_PATH.relative_to(REPO_ROOT)} in sync with discovered entries "
            f"(REST={len(rest_entries)} CLI={len(cli)} MCP={len(mcp_entries)} A2A={len(a2a_entries)} Skills={valid_skill_count})"
        )
        return 0

    for path, content in files.items():
        write_text_if_changed(path, content)
    remove_extra_mcp_files(expected_mcp_paths)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(doc_content, encoding="utf-8")
    valid_skill_count = len([skill for skill in skills if "error" not in skill and is_live(skill)])
    print(
        f"[contract] generated: {DOC_PATH.relative_to(REPO_ROOT)} "
        f"(REST={len(rest_entries)} CLI={len(cli)} MCP={len(mcp_entries)} A2A={len(a2a_entries)} Skills={valid_skill_count})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
