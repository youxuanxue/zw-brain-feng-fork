#!/usr/bin/env python3
"""修复「存量用户首次 IAM 登录产生两套用户数据」的历史脏数据（试用现场一次性维护脚本）。

背景
====
修复前的登录链路（PR 之前）有缺陷：存量用户（legacy import 以 pub_user.ID 为
`external_actor_id`、`status=iam_account_missing`）首次走 IAM OIDC 登录时，`upsert_actor`
按真实 `sub` 另插一行（`source_ref='iaf:claims'`），存量行从不被 rekey/合并 —— 于是同一个人
在 `actor_projection` 里留下**两行**：一行 legacy（user_id 键、含完整 profile + 角色绑定），
一行登录薄行（sub 键、只有 claims 字段）。页面用薄行 + token 角色照常工作，所以肉眼看不出，
但库里是两套数据、角色↔IAM 关联错位。

本脚本把这类历史双行**就地合并为一行**：
  1. 对每条 `source_ref='iaf:claims'` 薄行，按 `profile.username`（辅以 phone/email）在
     `{iam_account_missing, unmatched}` 状态的存量行里唯一匹配；
  2. 命中恰一条 → 删薄行 → 调 `claim_legacy_actor_by_iaf(legacy_actor_ref=...)` 把存量行
     rekey 到该 sub（同 PK、保留富 profile、搬移 binding + legacy_object_mapping）；
  3. 0 命中 / 多命中 → 只报告（unmatched / ambiguous），**绝不动数据**（fail-closed）。

代码侧根因已在 PR 内修复（登录/重导入统一走 claim_legacy_actor_by_iaf）；本脚本只清存量脏数据。

幂等性
======
重跑安全：rekey 后存量行 `source_ref` 仍是 legacy 值（非 `iaf:claims`），不会再被当薄行处理；
被认领的存量行已 rekey 到 sub、不再以 user_id 命中。再跑即 no-op。

安全
====
- 默认 `--dry-run`，只报告不写盘；`--apply` 才落库。
- 删除只经 `delete_actor_row(..., source_ref_guard='iaf:claims')`，守卫保证只能删登录薄行、
  永不误删 legacy/import 行。
- 远端试用库用 `--db-url`（如 `sqlite:////abs/path/zw_brain.db` 或 postgres URL）指定。
- **跑前务必备份库**（见 docs/deployment/m0-site-migration.md 修复 runbook）。

退出码
======
0=clean（无双行，或全部成功合并、无 unmatched/ambiguous）；
1=needs-human（存在 unmatched 或 ambiguous，需人工核对后再处理）；
2=apply-error（合并过程中抛错，已部分处理，需查 report + 备份回滚）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_CLAIMABLE_STATUSES = {"iam_account_missing", "unmatched"}
_THIN_SOURCE_REF = "iaf:claims"


def _profile(record: Any) -> dict[str, Any]:
    prof = getattr(record, "profile_json", None)
    return prof if isinstance(prof, dict) else {}


def _matches_legacy(legacy_profile: dict[str, Any], thin_profile: dict[str, Any]) -> bool:
    """同 governance_projection._match_legacy_actor_in_session 的辅助匹配谓词，离线复刻。"""
    username = thin_profile.get("username")
    account = legacy_profile.get("account")
    if username and account and str(username) == str(account):
        return True
    phone = thin_profile.get("phone")
    if phone and str(phone) and str(phone) in {str(legacy_profile.get("phone") or ""), str(legacy_profile.get("mobile") or "")}:
        return True
    email = thin_profile.get("email")
    if email and str(email) and str(email) == str(legacy_profile.get("email") or ""):
        return True
    return False


def _plan(actors: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """对每条薄行算出合并计划，按 outcome 分桶（不写库）。"""
    thin_rows = [a for a in actors if str(getattr(a, "source_ref", "") or "") == _THIN_SOURCE_REF]
    legacy_candidates = [
        a
        for a in actors
        if str(getattr(a, "source_ref", "") or "") != _THIN_SOURCE_REF
        and str(getattr(a, "status", "") or "") in _CLAIMABLE_STATUSES
    ]
    buckets: dict[str, list[dict[str, Any]]] = {"rekey": [], "unmatched": [], "ambiguous": []}
    for thin in thin_rows:
        thin_prof = _profile(thin)
        matches = [
            legacy
            for legacy in legacy_candidates
            if legacy.external_actor_id != thin.external_actor_id and _matches_legacy(_profile(legacy), thin_prof)
        ]
        unique = {m.external_actor_id: m for m in matches}
        entry = {
            "iaf_sub": thin.external_actor_id,
            "thin_username": thin_prof.get("username"),
            "legacy_refs": sorted(unique.keys()),
        }
        if len(unique) == 1:
            legacy = next(iter(unique.values()))
            entry["legacy_actor_ref"] = legacy.external_actor_id
            entry["thin_profile"] = thin_prof
            entry["thin_role_codes"] = list(getattr(thin, "role_codes_json", None) or [])
            entry["thin_display_name"] = getattr(thin, "display_name", None)
            entry["thin_org_code"] = getattr(thin, "org_code", None)
            buckets["rekey"].append(entry)
        elif len(unique) == 0:
            buckets["unmatched"].append(entry)
        else:
            buckets["ambiguous"].append(entry)
    return buckets


def _count_bindings(repo: Any, external_actor_id: str, *, tenant_id: str) -> int:
    return len(repo.list_actor_org_role_bindings(tenant_id=tenant_id, external_actor_id=external_actor_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant-id", default="sd-default", help="目标租户（默认 sd-default）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只报告不写盘（默认）")
    mode.add_argument("--apply", action="store_true", help="实际执行合并")
    parser.add_argument("--db-url", default=None,
                        help="覆盖 ZW_BRAIN_DATABASE_URL（如 sqlite:////abs/zw_brain.db）。不传则用环境默认库")
    parser.add_argument("--json-report", type=Path, default=None, help="把完整报告写到该 json 文件")
    args = parser.parse_args(argv)

    apply = bool(args.apply)
    tenant_id = args.tenant_id

    # 必须在 import repo（创建 engine 缓存）之前注入 db url。
    if args.db_url:
        os.environ["ZW_BRAIN_DATABASE_URL"] = args.db_url

    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository

    repo = GovernanceProjectionRepository()
    actors = repo.list_actors(tenant_id=tenant_id)
    buckets = _plan(actors)

    summary: dict[str, Any] = {
        "tenant_id": tenant_id,
        "mode": "apply" if apply else "dry-run",
        "actor_total": len(actors),
        "thin_rows": len(buckets["rekey"]) + len(buckets["unmatched"]) + len(buckets["ambiguous"]),
        "planned_rekey": len(buckets["rekey"]),
        "unmatched": len(buckets["unmatched"]),
        "ambiguous": len(buckets["ambiguous"]),
        "rekeyed": 0,
        "deleted_thin": 0,
        "bindings_moved": 0,
        "mappings_updated_for": [],
        "errors": [],
        "detail": {
            "rekey": buckets["rekey"],
            "unmatched": buckets["unmatched"],
            "ambiguous": buckets["ambiguous"],
        },
    }

    exit_code = 0
    if buckets["unmatched"] or buckets["ambiguous"]:
        exit_code = 1

    if apply:
        for plan in buckets["rekey"]:
            iaf_sub = plan["iaf_sub"]
            legacy_ref = plan["legacy_actor_ref"]
            try:
                moved_before = _count_bindings(repo, legacy_ref, tenant_id=tenant_id)
                # UQ(tenant, external_actor_id) 不容许 sub 同时存在两行：先删薄行，再把存量行 rekey 到 sub。
                deleted = repo.delete_actor_row(iaf_sub, tenant_id=tenant_id, source_ref_guard=_THIN_SOURCE_REF)
                if deleted:
                    summary["deleted_thin"] += 1
                repo.claim_legacy_actor_by_iaf(
                    iaf_sub=iaf_sub,
                    legacy_actor_ref=legacy_ref,
                    claims_profile=plan.get("thin_profile") or {},
                    token_role_codes=plan.get("thin_role_codes") or [],
                    display_name=plan.get("thin_display_name"),
                    org_code=plan.get("thin_org_code"),
                    tenant_id=tenant_id,
                )
                summary["rekeyed"] += 1
                summary["bindings_moved"] += moved_before
                summary["mappings_updated_for"].append(legacy_ref)
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append({"iaf_sub": iaf_sub, "legacy_actor_ref": legacy_ref, "error": f"{type(exc).__name__}: {exc}"})
                exit_code = 2

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    line = (
        f"[{summary['mode']}] tenant={tenant_id} actor_total={summary['actor_total']} "
        f"thin_rows={summary['thin_rows']} planned_rekey={summary['planned_rekey']} "
        f"rekeyed={summary['rekeyed']} deleted_thin={summary['deleted_thin']} "
        f"unmatched={summary['unmatched']} ambiguous={summary['ambiguous']} errors={len(summary['errors'])}"
    )
    print(line, file=sys.stderr)
    if not apply and summary["planned_rekey"]:
        print(f"[dry-run] {summary['planned_rekey']} 双行可合并；加 --apply 执行（务必先备份库）。", file=sys.stderr)
    if buckets["unmatched"]:
        print(f"[needs-human] {len(buckets['unmatched'])} 薄行未匹配到存量行 — 人工核对 username/phone/email 后处理。", file=sys.stderr)
    if buckets["ambiguous"]:
        print(f"[needs-human] {len(buckets['ambiguous'])} 薄行命中多条存量行 — 不自动合并，人工裁决。", file=sys.stderr)
    if summary["errors"]:
        print(f"[apply-error] {len(summary['errors'])} 行合并抛错，查 --json-report 并核对备份。", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
