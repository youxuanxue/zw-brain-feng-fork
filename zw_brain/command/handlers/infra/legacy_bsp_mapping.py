"""infra `legacy.bsp.mapping.import` handler — import_legacy_bsp_mapping 物理迁出（F1 turn 3）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def _normalize_candidates(input_payload: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = input_payload.get("mapping_manifest") if isinstance(input_payload.get("mapping_manifest"), dict) else {}
        manifest_version = input_payload.get("manifest_version") or manifest.get("manifest_version") or manifest.get("version") or "inline-v1"
        manifest_source_ref = input_payload.get("manifest_source_ref") or manifest.get("source_ref") or "legacy:bsp:mapping-manifest:inline-v1"
        manifest_rows = manifest.get("rows") if isinstance(manifest.get("rows"), list) else None
        source_rows = input_payload.get("candidates") or ([input_payload] if input_payload.get("legacy_permission_ref") else (manifest_rows or input_payload.get("rows") or []))
        normalized = []
        for item in source_rows:
            row = dict(item)
            normalized.append(
                {
                    "legacy_permission_ref": str(row.get("legacy_permission_ref") or ""),
                    "legacy_role_ref": row.get("legacy_role_ref"),
                    "capability_id": str(row.get("capability_id") or ""),
                    "surface": row.get("surface"),
                    "evidence_json": row.get("evidence_json") or row.get("manifest_evidence_json") or {},
                    "candidate_status": row.get("candidate_status") or "pending_review",
                    "mapping_status": row.get("mapping_status") or "mapped",
                    "source_ref": row.get("source_ref") or f"legacy:bsp:{row.get('legacy_permission_ref') or 'unknown'}",
                    "legacy_object_ref": row.get("legacy_object_ref") or str(row.get("legacy_permission_ref") or ""),
                    "manifest_version": row.get("manifest_version") or manifest_version,
                    "manifest_source_ref": row.get("manifest_source_ref") or manifest_source_ref,
                }
            )
        return normalized

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        from zw_brain.command.brain import BrainServiceError  # noqa: PLC0415 — avoid circular import at module load

        mode = str(payload.get("mode", payload.get("operation", "apply"))).lower()
        if mode not in {"dry-run", "dry_run", "apply"}:
            raise BrainServiceError(f"unsupported import mode: {mode}")
        dry_run = mode in {"dry-run", "dry_run"}
        tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT_ID))
        repo = deps.repos.governance_projection
        capability_manifests = brain.manifests()

        candidates_payload = _normalize_candidates(payload)
        block_issues = {"iam_account_missing": 0, "unmatched": 0, "unmapped_permission": 0}
        counters = {
            "source_count": len(candidates_payload),
            "projection_count": 0,
            "mapping_count": 0,
            "skip_count": 0,
            "failure_count": 0,
        }
        preview_items: list[dict[str, Any]] = []

        for item in candidates_payload:
            manifest_version = str(item.get("manifest_version") or "inline-v1")
            manifest_source_ref = str(item.get("manifest_source_ref") or "legacy:bsp:mapping-manifest:inline-v1")
            raw_evidence = brain._safe_json(item.get("evidence_json") or {})
            reviewable_evidence = {
                key: value
                for key, value in raw_evidence.items()
                if key not in {"menu_tree", "button_permission_tree", "permission_sql", "sql", "legacy_menu", "legacy_url", "route_component"}
            }
            evidence = reviewable_evidence | {
                "manifest_version": manifest_version,
                "manifest_source_ref": manifest_source_ref,
            }
            status = str(item.get("candidate_status") or "pending_review")
            capability_id = str(item.get("capability_id") or "")
            legacy_permission_ref = str(item.get("legacy_permission_ref") or "")
            source_ref = str(item.get("source_ref") or f"legacy:bsp:{legacy_permission_ref or 'unknown'}")
            mapping_status = str(item.get("mapping_status") or "mapped")
            skip_reason = None

            if status in {"iam_account_missing", "unmatched", "disabled"}:
                if status == "iam_account_missing":
                    block_issues["iam_account_missing"] += 1
                else:
                    block_issues["unmatched"] += 1
                counters["skip_count"] += 1
                skip_reason = status
            elif not capability_id or capability_id not in capability_manifests:
                block_issues["unmapped_permission"] += 1
                counters["failure_count"] += 1
                skip_reason = "unmapped_permission"
            else:
                counters["projection_count"] += 1
                counters["mapping_count"] += 1
                if not dry_run:
                    repo.import_legacy_policy_candidate(
                        {
                            "legacy_system": item.get("legacy_system") or "dsp-bsp",
                            "legacy_permission_ref": legacy_permission_ref,
                            "legacy_role_ref": item.get("legacy_role_ref"),
                            "capability_id": capability_id,
                            "surface": item.get("surface"),
                            "candidate_status": status,
                            "evidence_json": evidence,
                        },
                        tenant_id=tenant_id,
                    )
                    repo.upsert_legacy_object_mapping(
                        {
                            "source_ref": source_ref,
                            "legacy_object_ref": item.get("legacy_object_ref") or legacy_permission_ref,
                            "legacy_system": item.get("legacy_system") or "dsp-bsp",
                            "legacy_object_type": item.get("legacy_object_type") or "permission",
                            "canonical_type": "capability",
                            "canonical_ref": capability_id,
                            "mapping_status": mapping_status,
                            "evidence_json": evidence,
                        },
                        tenant_id=tenant_id,
                    )

            preview_items.append(
                {
                    "legacy_permission_ref": legacy_permission_ref,
                    "legacy_role_ref": item.get("legacy_role_ref"),
                    "capability_id": capability_id,
                    "surface": item.get("surface"),
                    "candidate_status": status,
                    "source_ref": source_ref,
                    "manifest_version": manifest_version,
                    "manifest_source_ref": manifest_source_ref,
                    "evidence_json": evidence,
                    "result": "skipped" if skip_reason else ("planned" if dry_run else "applied"),
                    "reason": skip_reason,
                }
            )

        deps.append_audit_feed("legacy.bsp.mapping.import", "legacy_policy_mapping_candidate", "warning" if counters["failure_count"] else "ok", actor)
        return {
            "mode": "dry-run" if dry_run else "apply",
            "tenant_id": tenant_id,
            "items": preview_items,
            "total": len(preview_items),
            "audit_id": audit_id,
            "summary": counters | {"blockers": block_issues},
        }

    return deps.write(ctx, payload, mutation)
