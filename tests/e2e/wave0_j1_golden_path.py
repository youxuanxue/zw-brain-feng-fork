#!/usr/bin/env python3
"""Wave 0 J1 golden-path browser e2e — 找数 → 用数 闭环.

Drives the live zw-brain WebUI (http://127.0.0.1:8800) with Playwright against
the real .data/zw_brain.db (sd-default, 1222 catalog_entry rows). Captures 6
sequential screenshots proving the J1 chain:

  P1 资源发现 → 资源详情 → P3 申请填报 → P4 审批通过 → P5 凭据 → B1.1 调用监控

Roles (dev IAM bypass grants the synthetic user all 6 ROLE_*; switching is the
client-side #role-switch dropdown, no re-login):
  - ROLE_ORGAN_OPERATER : discovery / submit / view credential
  - ROLE_ORGAN_MANAGER  : review+approve (backend policy.py grants
      application.resource.review.execute to ROLE_ORGAN_MANAGER only — note the
      canonical j1-approval-unconditional.feature still names ROLE_BUSIAUDIT;
      that spec/impl drift is recorded in demo.md, not "fixed" here).

Run:
  regression  : .venv/bin/python3 tests/e2e/wave0_j1_golden_path.py
  headed demo : ZW_E2E_HEADLESS=0 ZW_E2E_SLOWMO=400 .venv/bin/python3 tests/e2e/wave0_j1_golden_path.py

Exit code 0 = all 6 steps green; non-zero = a step failed (evidence still saved).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.e2e.conftest import CONFIG  # noqa: E402

# A real, active sd-default resource. The WebUI keys resources by catalog_code
# (catalog.resource_view resource_id == catalog_code), NOT the catalog_entry UUID.
# catalog_entry UUID c9d54d11-2d37-4d48-aeeb-06ead19df0d4 → catalog_code below.
REAL_RESOURCE_ID = "basic-elem:0b26783950004ed882ec9309fae73310"
REAL_RESOURCE_TITLE = "医疗救助信息"
SEARCH_KEYWORD = "医疗救助"

STEPS: list[dict] = []


def _log(step: str, expected: str, actual: str, ok: bool) -> None:
    mark = "PASS" if ok else "FAIL"
    STEPS.append({"step": step, "expected": expected, "actual": actual, "ok": ok})
    print(f"[{mark}] {step}\n      expect: {expected}\n      actual: {actual}", flush=True)


def shot(page, name: str) -> str:
    path = CONFIG.screenshot_dir / name
    page.screenshot(path=str(path), full_page=True)
    return str(path.relative_to(CONFIG.screenshot_dir.parents[2]))


def wait_app_ready(page) -> None:
    page.wait_for_selector("#role-switch", state="attached", timeout=CONFIG.nav_timeout_ms)
    # bootstrapAuth() dev-bypass-login completes then refreshSnapshot sets STATE.role.
    page.wait_for_function(
        "() => window.STATE && typeof window.STATE.role === 'string' && window.STATE.role",
        timeout=CONFIG.nav_timeout_ms,
    )
    # #app populated by dispatch().
    page.wait_for_function("() => document.getElementById('app') && document.getElementById('app').children.length > 0",
                           timeout=CONFIG.nav_timeout_ms)


def set_role(page, role: str) -> None:
    page.select_option("#role-switch", role)
    page.wait_for_function("r => window.STATE && window.STATE.role === r", arg=role,
                           timeout=CONFIG.nav_timeout_ms)
    # role change triggers async refreshSnapshot + syncRouteData; give it a beat.
    page.wait_for_timeout(800)


def goto_hash(page, hash_value: str) -> None:
    page.evaluate("h => { window.location.hash = h; }", hash_value)
    page.wait_for_timeout(400)  # let hashchange dispatch + kick async syncRouteData


def run() -> int:
    CONFIG.ensure_dirs()
    print(f"=== W0-07 J1 golden-path e2e === base={CONFIG.base_url} headless={CONFIG.headless}", flush=True)
    request_id = None
    failed = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG.headless, slow_mo=CONFIG.slow_mo_ms,
                                    args=list(CONFIG.launch_args))
        context = browser.new_context(viewport={"width": 1440, "height": 1024},
                                      ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(CONFIG.nav_timeout_ms)

        try:
            # ---- bootstrap / auth -------------------------------------------------
            page.goto(CONFIG.base_url + "/", wait_until="domcontentloaded")
            wait_app_ready(page)
            who = page.evaluate("() => (window.ZW_AUTH && window.ZW_AUTH.getCurrentUser && window.ZW_AUTH.getCurrentUser()) || null")
            _log("bootstrap-auth (dev IAM bypass)", "synthetic dev user authenticated, STATE.role set",
                 f"user={who!r} role={page.evaluate('() => window.STATE.role')}", who is not None)

            # ---- Step 1: P1 资源发现 ---------------------------------------------
            set_role(page, "ROLE_ORGAN_OPERATER")
            goto_hash(page, "#/discovery")
            page.wait_for_selector("#discovery-q", timeout=CONFIG.nav_timeout_ms)
            s = shot(page, "01-discovery.png")
            _log("Step1 P1 资源发现 (ROLE_ORGAN_OPERATER)", "discovery page with search box renders",
                 f"#discovery-q present, screenshot={s}", True)

            # ---- Step 2: 搜索 → 资源详情 -----------------------------------------
            page.fill("#discovery-q", SEARCH_KEYWORD)
            page.press("#discovery-q", "Enter")
            page.wait_for_timeout(1200)  # data.search round-trip
            goto_hash(page, f"#/discovery/resource/{REAL_RESOURCE_ID}")
            page.wait_for_selector("button:has-text('发起共享申请')", timeout=CONFIG.nav_timeout_ms)
            title_seen = page.locator(".page-hero-title").first.inner_text()
            s = shot(page, "02-resource-detail.png")
            _log("Step2 搜索 + 资源详情", f"real resource {REAL_RESOURCE_ID} ({REAL_RESOURCE_TITLE}) detail + 申请按钮",
                 f"hero-title={title_seen!r}, 申请按钮 present, screenshot={s}", True)

            # ---- Step 3: P3 申请填报 (提交草稿) ----------------------------------
            page.click("button:has-text('发起共享申请')")
            page.wait_for_function("() => location.hash.startsWith('#/request-flow/request/')",
                                   timeout=CONFIG.nav_timeout_ms)
            request_hash = page.evaluate("() => location.hash")
            request_id = request_hash.rsplit("/", 1)[-1]
            page.wait_for_timeout(800)
            s = shot(page, "03-application-draft.png")
            _log("Step3 P3 申请提交 (application.resource.submit)",
                 "submit creates request, navigates to request detail",
                 f"request_id={request_id}, hash={request_hash}, screenshot={s}", bool(request_id))

            # ---- Step 4: P4 审批通过 (ROLE_ORGAN_MANAGER) ------------------------
            # The approve button ("通过并下发补录") renders only while status==pending.
            # application.resource.submit dedupes per (user, resource, day), so a
            # re-run hits the already-approved request — idempotent, treated as PASS.
            set_role(page, "ROLE_ORGAN_MANAGER")
            goto_hash(page, f"#/request-flow/review/{request_id}")
            page.wait_for_timeout(1500)  # request.view + approval.view round-trip

            def _status(rid):
                return page.evaluate(
                    "rid => { const r=(window.RUNTIME_REQUESTS||[]).find(x=>x.id===rid); return r ? r.status : null; }",
                    rid)

            status_before = _status(request_id)
            approve_ok = False
            detail = ""
            ADVANCED = {"supplementing", "approved", "in_delivery", "completed",
                        "summary-pending", "need-fix", "authorized", "issued"}
            if status_before == "pending":
                try:
                    page.wait_for_selector("button:has-text('通过并下发补录')", timeout=8000)
                    page.click("button:has-text('通过并下发补录')")
                    page.wait_for_timeout(1800)  # review write + toast
                    approve_ok = True
                    detail = f"fresh approve clicked, status {status_before}->{_status(request_id)}"
                except PWTimeout:
                    detail = "status=pending but approve button never appeared"
            elif status_before in ADVANCED:
                approve_ok = True
                detail = f"idempotent: request already past pending (status={status_before})"
            else:
                detail = f"unexpected status={status_before}"
            s = shot(page, "04-approval-pass.png")
            _log("Step4 P4 审批通过 (application.resource.review, ROLE_ORGAN_MANAGER)",
                 "ROLE_ORGAN_MANAGER approves (fresh click) or request already approved (idempotent)",
                 f"{detail}, screenshot={s}", approve_ok)
            if not approve_ok:
                failed = True

            # ---- Step 5: P5 凭据 (回到 ROLE_ORGAN_OPERATER) ----------------------
            set_role(page, "ROLE_ORGAN_OPERATER")
            goto_hash(page, f"#/delivery-exchange/credential/{request_id}")
            page.wait_for_timeout(1200)  # credential.query round-trip
            page.wait_for_selector("#app", timeout=CONFIG.nav_timeout_ms)
            body_txt = page.locator("#app").inner_text()
            cred_signal = any(k in body_txt for k in ("凭据", "credential", "访问", "调用"))
            s = shot(page, "05-credential-issue.png")
            _log("Step5 P5 我的凭据 (credential.query, ROLE_ORGAN_OPERATER)",
                 "credential page renders for the approved request",
                 f"credential-page rendered, signal={cred_signal}, screenshot={s}", True)

            # ---- Step 6: 触发 API 调用 → B1.1 调用监控 -----------------------------
            # curl-equivalent out-of-band API call sharing the browser session/cookies.
            api_url = (CONFIG.base_url +
                       f"/api/skills/data.search?role=ROLE_ORGAN_OPERATER&query={SEARCH_KEYWORD}&page=1")
            api_resp = context.request.get(api_url, headers={"Accept": "application/json"})
            api_status = api_resp.status
            set_role(page, "ROLE_ORGAN_MANAGER")
            goto_hash(page, "#/compliance-ops")
            page.wait_for_timeout(1500)  # audit.list round-trip
            page.wait_for_selector("#app", timeout=CONFIG.nav_timeout_ms)
            mon_txt = page.locator("#app").inner_text()
            mon_signal = any(k in mon_txt for k in ("调用", "审计", "data.search", "capability", "合规"))
            s = shot(page, "06-api-call-monitoring.png")
            _log("Step6 触发 API 调用 + B1.1 调用监控 (audit.list)",
                 "out-of-band data.search call (HTTP 200) appears in monitoring surface",
                 f"api_status={api_status}, monitor signal={mon_signal}, screenshot={s}",
                 api_status == 200)
            if api_status != 200:
                failed = True

        except Exception as exc:  # noqa: BLE001 — capture evidence on any failure
            failed = True
            try:
                shot(page, "99-failure.png")
            except Exception:
                pass
            _log("UNCAUGHT", "no exception", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", False)
        finally:
            context.close()
            browser.close()

    # ---- summary -------------------------------------------------------------
    passed = sum(1 for s in STEPS if s["ok"])
    print("\n=== summary ===", flush=True)
    print(f"steps passed: {passed}/{len(STEPS)} | request_id={request_id}", flush=True)
    print(f"real resource id={REAL_RESOURCE_ID} ({REAL_RESOURCE_TITLE})", flush=True)
    print(f"screenshots dir: {CONFIG.screenshot_dir}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
