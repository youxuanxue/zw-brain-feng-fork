"""J1 credential handlers — 3 cap (issue / query / sample.render)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


import copy
import json as _json

import zw_brain.shared.clock as clock
from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.resource_kind import canonical_resource_kind

# 监控入口：链接到 §3.4 集团运维监控（不内嵌 dashboard），由 IT 资源运维直观接管
_MONITORING_DASHBOARD_LINK = "https://ops.gov-data.local/monitoring/credential-call?app_key={app_key}"


def _resolve_resource_kind(deps, resource_id: str | None) -> str | None:
    """据交付资源 id 反查物化形态（库表/文件/API）；用于「查看授权」按类型化呈现（F5）。

    经 ``canonical_resource_kind`` 读路径折叠（D53 单一事实源）——存量库 legacy
    ``service`` 归 ``api``、``folder/url/link`` 归 ``file``，未知/空 → None（诚实未知，
    前端按通用「凭据」兜底，不臆断为 API）。不折叠则 legacy ``service`` 形态的接口资源
    会漏判成非 API、前端显通用「凭据」而非「网关授权码」。
    """
    if not resource_id:
        return None
    repo = getattr(deps.repos, "resource_api", None)
    if repo is None:
        return None
    try:
        asset = repo.get_asset(str(resource_id))
    except Exception:  # noqa: BLE001 — 只读旁路，查不到不破凭据主路径
        return None
    if asset is None:
        return None
    return canonical_resource_kind(getattr(asset, "resource_kind", None))


def _credential_resource_kind(deps, delivery: dict[str, Any], resource_id: str | None = None) -> str | None:
    """凭据页资源类型(库表/文件/API) — 优先用交付任务已归一的 ``resourceKind``(F3 同源，
    含 channel 兜底)，保证「领数据」列表与凭据页**口径一致**(同一任务两页不会一边 API 一边
    凭据)；缺则反查资源主表(canonical 折叠)。两路都查不到 → None(前端按通用「凭据」诚实
    兜底，不臆断为 API)。"""
    kind = canonical_resource_kind(delivery.get("resourceKind"))
    if kind is not None:
        return kind
    return _resolve_resource_kind(deps, resource_id if resource_id is not None else delivery.get("resourceId"))


def _credential_unissued_hint(kind: str | None) -> str:
    """未签发文案随资源类型走(F5-W1) — API 资源凭据语义即「授权(网关授权码)」，其余库表/
    文件是「凭据」。与页头名词(authNoun)同源，避免「凭据」页面配「授权尚未签发」自相矛盾。"""
    noun = "授权" if kind == "api" else "凭据"
    return f"{noun}尚未签发；请等待审批通过或联系审批人手工签发。"

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _issue_credential(brain, deps, ctx, request_id: str, role: str, confirmed: bool, *, reissue: bool = False) -> dict[str, Any]:
    """签发凭据 — 审批通过自动触发，或审批人/主管部门手工补签。"""
    request = deps.view.requests.find_by_id(request_id)
    delivery = deps.view.delivery.find_by_request_id(request_id)
    if delivery is None:
        raise NotFoundError(request_id)
    # 仅审批通过的 request 才能签发（前置守卫）。
    # 覆盖所有"审批已通过"语义的状态：approved（同步落库即时态）/ supplementing（基层补差中）
    # / summary-pending（汇总确认中）/ completed（已完成）/ in_delivery（交付进行中）/ granted（已授权）
    approved_states = {"approved", "supplementing", "summary-pending", "completed", "in_delivery", "granted"}
    if request.get("status") not in approved_states:
        raise InvalidStateError(f"request {request_id} not approved yet; current status={request.get('status')}")

    existing = (delivery.get("accessGrantSnapshot") or {}).get("credential")
    if existing and not reissue:
        return {
            "request_id": request_id,
            "credential": existing,
            "audit_id": delivery.get("accessGrantSnapshot", {}).get("issued_audit_id"),
            "issued_via": "cached",
        }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        # R-002 fix: reissue 路径传 audit_id 作 seed → 真生成新 app_secret（旧 secret 立即失效语义）
        seed = audit_id if existing else None
        credential = deps.services.request.credential_for_request(request_id, seed=seed)
        grant_snapshot = copy.deepcopy(delivery.get("accessGrantSnapshot") or {})
        grant_snapshot["credential"] = credential
        grant_snapshot["issued_audit_id"] = audit_id
        grant_snapshot["issued_at"] = clock.now_datetime()
        grant_snapshot["issued_by"] = actor
        delivery["accessGrantSnapshot"] = grant_snapshot
        delivery.setdefault("history", []).append({
            "time": clock.now_short_time(),
            "state": "凭据已签发" if not existing else "凭据已重新签发（旧 secret 立即失效）",
            "detail": f"app_key={credential['app_key']}（平台自签凭据），可在 P4 凭据领取页查看。",
        })
        deps.append_audit_feed("credential.issue", request_id, "ok", actor)
        return {
            "request_id": request_id,
            "credential": credential,
            "audit_id": audit_id,
            "issued_via": "manual-reissue" if existing else "auto-on-approval",
        }

    return deps.write(ctx, {"request_id": request_id, "reissue": reissue}, mutation)

def _get_credential(brain, deps, ctx, request_id: str, role: str) -> dict[str, Any]:
    """P4 凭据领取页查询入口 — 申请人 / 审批人 / 审计员都可查（无侧效，仅读）。"""
    # 权限校验由 manifest + enforce_manifest_policy 走 invoke_skill 路径处理
    delivery = deps.view.delivery.find_by_request_id(request_id)
    if delivery is None:
        raise NotFoundError(request_id)
    snapshot = delivery.get("accessGrantSnapshot") or {}
    credential = snapshot.get("credential")
    if not credential:
        kind = _credential_resource_kind(deps, delivery)
        return {
            "request_id": request_id,
            "credential": None,
            "status": "not_issued",
            "resource_kind": kind,
            "hint": _credential_unissued_hint(kind),
        }
    resource_id = delivery.get("resourceId")
    resource_name = delivery.get("resourceName")
    if not resource_name or not resource_id:
        request = deps.view.requests.find_by_id(request_id)
        if request is not None:
            resource_name = resource_name or request.get("resourceName")
            resource_id = resource_id or request.get("resourceId")
    return {
        "request_id": request_id,
        "credential": credential,
        "status": "issued",
        "issued_audit_id": snapshot.get("issued_audit_id"),
        "issued_at": snapshot.get("issued_at"),
        "issued_by": snapshot.get("issued_by"),
        "resource_id": resource_id,
        "resource_name": resource_name,
        # F5：物化形态——API 资源把「凭据」按「网关授权码」呈现，前端据此切换文案。
        # 与交付列表同源(F3 resourceKind 优先)，保证两页口径一致。
        "resource_kind": _credential_resource_kind(deps, delivery, resource_id),
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def _render_credential_samples(brain, deps, ctx, request_id: str, role: str) -> dict[str, Any]:
    """渲染 credential 的 curl / Python / Java 三语调用样例 + 配额 + 监控入口（只读）.

    F5: P4 凭据领取生产化。基于已签发 credential + 真实 sd-default 资源 schema 渲染
    可复制粘贴的端到端调用样例。监控入口仅链接到 §3.4 集团运维监控（不内嵌 dashboard）。

    所有字段从 _get_credential 派生；不存储样例（每次按需渲染）。
    """
    credential_view = _get_credential(brain, deps, ctx, request_id, role)
    if credential_view.get("credential") is None:
        return {
            "request_id": request_id,
            "samples": None,
            "status": credential_view.get("status", "not_issued"),
            "hint": credential_view.get("hint", "凭据尚未签发，无法渲染调用样例。"),
        }
    cred = credential_view["credential"]
    app_key = str(cred.get("app_key") or "")
    app_secret = str(cred.get("app_secret") or "")
    resource_id = str(credential_view.get("resource_id") or "")
    resource_name = str(credential_view.get("resource_name") or "")
    invoke_url = str(cred.get("invoke_url_template") or "").replace(
        "<resource_code>", resource_id or "<resource_code>"
    )
    quota_per_day = int(cred.get("quota_per_day") or 1000)

    headers = {
        "X-App-Key": app_key,
        "X-App-Secret": app_secret,
        "Accept": "application/json",
    }
    # Real call body keyed off resource schema (sd-default catalog hint)
    body_example = {
        "filters": {"limit": 10, "offset": 0},
        "fields": ["id", "name", "value", "updated_at"],
        "tenant_id": "sd-default",
    }

    curl_sample = (
        f"# {resource_name or resource_id or 'resource'} — quota_per_day={quota_per_day}\n"
        f"curl -X POST '{invoke_url}' \\\n"
        f"  -H 'X-App-Key: {app_key}' \\\n"
        f"  -H 'X-App-Secret: {app_secret}' \\\n"
        f"  -H 'Content-Type: application/json' \\\n"
        f"  -d '{_json.dumps(body_example, ensure_ascii=False)}'\n"
    )

    python_sample = (
        f"# {resource_name or resource_id or 'resource'} — quota_per_day={quota_per_day}\n"
        f"import requests\n"
        f"resp = requests.post(\n"
        f"    {invoke_url!r},\n"
        f"    headers={_json.dumps(headers, ensure_ascii=False)},\n"
        f"    json={_json.dumps(body_example, ensure_ascii=False)},\n"
        f"    timeout=30,\n"
        f")\n"
        f"resp.raise_for_status()\n"
        f"print(resp.json())\n"
    )

    body_json_for_java = _json.dumps(body_example, ensure_ascii=False).replace('"', '\\"')
    java_sample = (
        f'// {resource_name or resource_id or "resource"} — quota_per_day={quota_per_day}\n'
        f'HttpClient client = HttpClient.newHttpClient();\n'
        f'String body = "{body_json_for_java}";\n'
        f'HttpRequest req = HttpRequest.newBuilder()\n'
        f'    .uri(URI.create({invoke_url!r}))\n'
        f'    .header("X-App-Key", {app_key!r})\n'
        f'    .header("X-App-Secret", {app_secret!r})\n'
        f'    .header("Content-Type", "application/json")\n'
        f'    .POST(HttpRequest.BodyPublishers.ofString(body))\n'
        f'    .build();\n'
        f'HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());\n'
        f'System.out.println(resp.body());\n'
    )

    monitoring_link = _MONITORING_DASHBOARD_LINK.format(app_key=app_key)

    deps.append_audit_feed("credential.sample.render", request_id, "ok",
                             ctx.actor or "system")

    return {
        "request_id": request_id,
        "status": "rendered",
        # F5：透传物化形态，前端「查看授权」样例区按 API 口径呈现网关调用示例。
        "resource_kind": credential_view.get("resource_kind"),
        "credential_excerpt": {
            "app_key": app_key,
            "valid_from": cred.get("valid_from"),
            "valid_to": cred.get("valid_to"),
            "quota_per_day": quota_per_day,
        },
        "resource_id": resource_id,
        "resource_name": resource_name,
        "invoke_url": invoke_url,
        "samples": {
            "curl": curl_sample,
            "python": python_sample,
            "java": java_sample,
        },
        "monitoring_link": monitoring_link,
        "monitoring_hint": "§3.4 集团运维监控承接调用数据；点击跳转外部 dashboard，本平台不内嵌。",
    }


def handler_credential_issue(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _issue_credential(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), reissue=bool(payload.get("reissue", False)))

def handler_credential_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_credential(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)))

def handler_credential_sample_render(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _render_credential_samples(brain, deps, ctx, str(payload["request_id"]), str(payload.get("role", ctx.role)))

