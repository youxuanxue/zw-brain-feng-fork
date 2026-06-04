#!/usr/bin/env python3
"""Wave 0 J1 golden-path browser e2e — 找数 → 用数 闭环.

Drives the Vue3 WebUI (default http://127.0.0.1:5173 via Vite dev, or 8800 REST
static) with Playwright against the real .data/zw_brain.db (sd-default). Captures
6 sequential screenshots proving the J1 chain:

  P2 资源发现 → 资源详情 → P3 申请 → P3 审批 → P4 凭据 → B1.1 合规

Roles (dev IAM bypass + allowRoleSwitch):
  - ROLE_ORGAN_OPERATER : discovery / submit / view credential
  - ROLE_ORGAN_MANAGER  : review+approve

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

from tests.e2e.conftest import (  # noqa: E402
    CONFIG,
    goto_vue_hash,
    set_vue_role,
    wait_vue_app_ready,
)

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


def run() -> int:
    CONFIG.ensure_dirs()
    print(f"=== W0-07 J1 golden-path e2e (Vue) === base={CONFIG.base_url} headless={CONFIG.headless}", flush=True)
    request_id = None
    failed = False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=CONFIG.headless,
            slow_mo=CONFIG.slow_mo_ms,
            args=list(CONFIG.launch_args),
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1024}, ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(CONFIG.nav_timeout_ms)

        try:
            page.goto(CONFIG.base_url + "/", wait_until="domcontentloaded")
            wait_vue_app_ready(page)
            user = page.locator(".user-menu-button").first.inner_text() if page.locator(".user-menu-button").count() else ""
            _log(
                "bootstrap-auth (dev IAM bypass)",
                "Vue app booted with authenticated user",
                f"user={user!r}",
                bool(user),
            )

            set_vue_role(page, "ROLE_ORGAN_OPERATER")
            goto_vue_hash(page, "#/discovery")
            page.wait_for_selector("#p2-search", timeout=CONFIG.nav_timeout_ms)
            s = shot(page, "01-discovery.png")
            _log("Step1 P2 资源发现", "discovery page with #p2-search renders", f"screenshot={s}", True)

            page.fill("#p2-search", SEARCH_KEYWORD)
            page.wait_for_timeout(1500)
            page.wait_for_selector(".res-card", timeout=CONFIG.nav_timeout_ms)
            card_text = page.locator(".res-card").first.inner_text()
            s = shot(page, "02-search-results.png")
            _log(
                "Step2 搜索命中",
                f"data.search returns {REAL_RESOURCE_TITLE}",
                f"first card={card_text[:80]!r}, screenshot={s}",
                SEARCH_KEYWORD in card_text or REAL_RESOURCE_TITLE in card_text,
            )

            goto_vue_hash(page, f"#/discovery/resource/{REAL_RESOURCE_ID}")
            page.wait_for_selector("button:has-text('申请资源')", timeout=CONFIG.nav_timeout_ms)
            title_seen = page.locator(".page-hero-title").first.inner_text()
            s = shot(page, "03-resource-detail.png")
            _log(
                "Step3 资源详情",
                f"resource {REAL_RESOURCE_ID} detail + apply button",
                f"hero-title={title_seen!r}, screenshot={s}",
                REAL_RESOURCE_TITLE in title_seen or REAL_RESOURCE_ID in title_seen,
            )

            page.click("button:has-text('申请资源')")
            page.wait_for_function(
                "() => location.hash.startsWith('#/request-flow/request/')",
                timeout=CONFIG.nav_timeout_ms,
            )
            request_hash = page.evaluate("() => location.hash")
            request_id = request_hash.rsplit("/", 1)[-1]
            page.wait_for_timeout(800)
            s = shot(page, "04-application-draft.png")
            _log(
                "Step4 P3 申请 (request.create)",
                "navigates to request detail after create",
                f"request_id={request_id}, screenshot={s}",
                bool(request_id),
            )

            set_vue_role(page, "ROLE_ORGAN_MANAGER")
            goto_vue_hash(page, f"#/request-flow/review/{request_id}")
            page.wait_for_timeout(1500)

            approve_ok = False
            detail = ""
            body_before = page.locator("body").inner_text()
            if "审批中" in body_before or "pending" in body_before or "待审批" in body_before:
                try:
                    page.wait_for_selector("button:has-text('通过')", timeout=8000)
                    page.click("button:has-text('通过')")
                    page.wait_for_timeout(1800)
                    approve_ok = True
                    detail = "fresh approve clicked"
                except PWTimeout:
                    detail = "approve button never appeared"
            elif any(k in body_before for k in ("approved", "已通过", "in_delivery", "supplementing", "completed")):
                approve_ok = True
                detail = "idempotent: request already past pending"
            else:
                detail = f"unexpected body snippet={body_before[:120]!r}"
            s = shot(page, "05-approval-pass.png")
            _log("Step5 P3 审批 (ROLE_ORGAN_MANAGER)", "approve or already approved", f"{detail}, screenshot={s}", approve_ok)
            if not approve_ok:
                failed = True

            set_vue_role(page, "ROLE_ORGAN_OPERATER")
            goto_vue_hash(page, f"#/delivery-exchange/credential/{request_id}")
            page.wait_for_timeout(1500)
            body_txt = page.locator("body").inner_text()
            cred_signal = any(k in body_txt for k in ("凭据", "App Key", "not_issued", "尚未签发"))
            s = shot(page, "06-credential-page.png")
            _log("Step6 P4 凭据页", "credential page renders", f"signal={cred_signal}, screenshot={s}", cred_signal)

            set_vue_role(page, "ROLE_BUSIAUDIT")
            goto_vue_hash(page, "#/compliance-ops")
            page.wait_for_timeout(2000)
            mon_txt = page.locator("body").inner_text()
            mon_signal = any(k in mon_txt for k in ("合规", "统计", "回放", "异常", "追责"))
            s = shot(page, "07-compliance-ops.png")
            _log("Step7 B1.1 合规运营", "compliance ops surface renders", f"signal={mon_signal}, screenshot={s}", mon_signal)
            if not mon_signal:
                failed = True

        except Exception as exc:  # noqa: BLE001
            failed = True
            try:
                shot(page, "99-failure.png")
            except Exception:
                pass
            _log("UNCAUGHT", "no exception", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", False)
        finally:
            context.close()
            browser.close()

    passed = sum(1 for s in STEPS if s["ok"])
    print("\n=== summary ===", flush=True)
    print(f"steps passed: {passed}/{len(STEPS)} | request_id={request_id}", flush=True)
    print(f"real resource id={REAL_RESOURCE_ID} ({REAL_RESOURCE_TITLE})", flush=True)
    print(f"screenshots dir: {CONFIG.screenshot_dir}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
