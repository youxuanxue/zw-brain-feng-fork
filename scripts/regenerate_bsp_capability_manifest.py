#!/usr/bin/env python3
"""Regenerate bsp-permission-sample capability-mapping-manifest.json from sample SQL."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / ".local/用户权限体系-new/bsp-permission-sample-20260520"
REG_DIR = REPO / "zw_brain/skill_registration/registered"

FUNC_MAP: dict[str, str | None] = {
    "FUNC_CATALOG_QUERY": "catalog.entry.query",
    "FUNC_CATALOG_CREATE": "catalog.entry.create",
    "FUNC_CATALOG_UPDATE": "catalog.entry.update",
    "FUNC_CATALOG_DELETE": "catalog.entry.withdraw",
    "FUNC_CATALOG_SUBMIT": "catalog.entry.submit_review",
    "FUNC_CATALOG_REVIEW": "catalog.entry.review",
    "FUNC_CATALOG_PUBLISH": "catalog.entry.publish",
    "FUNC_RESOURCE_BIND": "catalog.resource.bind",
    "FUNC_RESOURCE_LIST": "resource.asset.query",
    "FUNC_REQUEST_CREATE": "request.create",
    "FUNC_REQUEST_SUBMIT": "request.submit",
    "FUNC_REQUEST_MY_LIST": "request.list",
    "FUNC_REQUEST_PENDING": "request.list",
    "FUNC_APPROVAL_DECIDE": "approval.case.decide",
    "FUNC_CREDENTIAL_QUERY": "credential.query",
    "FUNC_CAPABILITY_REGISTER": "package.register_version",
    "FUNC_GOVERN_QUALITY": "ops.catalog.quality.query",
    "FUNC_CATEGORY_MANAGE": "catalog.group.query",
    "FUNC_AUDIT_LIST": "audit.list",
    "FUNC_SECURITY_AUDIT_LIST": "audit.list",
    "FUNC_SECURITY_REPORT": "ops.service.report.query",
    "FUNC_EVIDENCE_CHAIN": "audit.replay_evidence_chain",
    "FUNC_EVIDENCE_REPLAY": "audit.replay_evidence_chain",
    "FUNC_OPERATION_LOG": "ops.gateway.log.anchor",
    "FUNC_DASHBOARD_VIEW": "workbench.view",
    "FUNC_ORGAN_LIST": "org.projection.sync",
    "FUNC_SYSTEM_MONITOR": "ops.gateway.heartbeat.ingest",
    "FUNC_OPS_REPORT": "ops.service.report.query",
    "FUNC_DATA_REPORT": "ops.catalog.statistics.query",
    "FUNC_SERVICE_LIST": "direct_access.catalog.query",
    "FUNC_SERVICE_APPLY": "request.create",
    "FUNC_SERVICE_APPROVE": "approval.case.decide",
    "FUNC_ZONE_LIST": "zone.list",
    "FUNC_ZONE_PUBLISH": "zone.publish_topic_projection",
    "FUNC_PORTAL_CATALOG": "catalog.browse",
    "FUNC_PORTAL_OVERVIEW": "workbench.view",
    "FUNC_DEMAND_MANAGE": "require.resource.match",
    "FUNC_DEMAND_PUBLISH": "require.task.handoff",
    "FUNC_SUPPLY_MANAGE": "require.resource.dispatch",
    "FUNC_CONNECT_MANAGE": "require.resource.match",
    "FUNC_REQUIRE_STATS": "ops.exchange.statistics.query",
    "FUNC_TASK_LIST": "ops.ticket.create",
    "FUNC_ALERT_LIST": "risk.event.ingest",
    "FUNC_LOG_LIST": "ops.gateway.log.anchor",
    "FUNC_SYNC_LIST": "legacy.migration.status.query",
    "FUNC_SYNC_EXECUTE": "legacy.bsp.mapping.import",
    "FUNC_SECURITY_ASSET": "security.scan.result.sync",
    "FUNC_SECURITY_RISK": "risk.event.ingest",
    "FUNC_PROFILE_VIEW": "system.snapshot",
}

RES_PATH_MAP: list[tuple[str, str]] = [
    ("/catalog/search", "catalog.entry.query"),
    ("/catalog/entry/create", "catalog.entry.create"),
    ("/catalog/entry/update", "catalog.entry.update"),
    ("/catalog/entry/submit", "catalog.entry.submit_review"),
    ("/catalog/review/execute", "catalog.entry.review"),
    ("/catalog/publish/execute", "catalog.entry.publish"),
    ("/catalog/resource/list", "resource.asset.query"),
    ("/catalog/request/create", "request.create"),
    ("/catalog/request/pending/list", "request.list"),
    ("/catalog/credential/list", "credential.query"),
    ("/bsp/system/audit/list", "audit.list"),
    ("/bsp/evidence/chain", "audit.replay_evidence_chain"),
    ("/bsp/dashboard", "workbench.view"),
    ("/portal/zone/list", "zone.list"),
]


def _registered_skills() -> set[str]:
    out: set[str] = set()
    for path in REG_DIR.glob("*.json"):
        out.add(json.loads(path.read_text(encoding="utf-8")).get("skill_id", ""))
    return out


def _row(ref: str, cap: str | None, *, kind: str = "function", path: str | None = None) -> dict:
    return {
        "legacy_permission_ref": ref,
        "legacy_permission_kind": kind,
        "legacy_role_ref": None,
        "legacy_name": ref,
        "legacy_path": path,
        "capability_id": cap,
        "permission": f"{cap}.execute" if cap else None,
        "surface": "webui",
        "candidate_status": "pending_review",
        "confidence": "needs_review",
        "mapping_reason": f"与 pub_role_{kind} 样本字段对齐",
        "evidence_json": {"source_tables": [f"pub_role_{kind}", "pub_function" if kind == "function" else "pub_resource"]},
    }


def main() -> None:
    registered = _registered_skills()
    text = (SAMPLE / "sample-dsp-bsp-permission.sql").read_text(encoding="utf-8")
    chunk = text[text.index("pub_role_function") :]
    func_codes = sorted({f for _, f in re.findall(r"\('([^']+)',\s*'(FUNC[^']+)'", chunk)})

    rows: list[dict] = []
    for code in func_codes:
        cap = FUNC_MAP.get(code)
        if cap and cap not in registered:
            cap = None
        if cap:
            rows.append(_row(code, cap))

    res_paths = {}
    for m in re.finditer(r"\('(RES\d+)',\s*'[^']*',\s*'[^']*',\s*'[^']*',\s*'([^']*)'", text):
        res_paths[m.group(1)] = m.group(2)
    for res_id, path in sorted(res_paths.items()):
        cap = None
        for prefix, cid in RES_PATH_MAP:
            if path.startswith(prefix):
                cap = cid if cid in registered else None
                break
        if cap:
            rows.append(_row(res_id, cap, kind="resource", path=path))

    manifest = {
        "manifest_type": "capability_mapping_manifest",
        "manifest_version": "bsp-capability-map-2026-05-20-v2",
        "legacy_system": "dsp-bsp",
        "tenant_id": "sd-default",
        "description": "legacy_permission_ref 与 pub_role_function.FUNCTION_CODE / pub_role_resource.RES_CODE 对齐；仅收录已绑定 capability_id 的候选。",
        "rows": rows,
        "statistics": {
            "total_mappings": len(rows),
            "with_capability_id": len(rows),
            "note": "无 capability_id 的 FUNCTION_CODE 在 dry-run 中由 pub_role_function 关系触发 unmapped_permission",
        },
    }
    out = SAMPLE / "capability-mapping-manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(rows)} rows")


if __name__ == "__main__":
    main()
