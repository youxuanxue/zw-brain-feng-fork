#!/usr/bin/env python3
"""F6/F8 P5 提供方子页 Playwright 冒烟 — inbox + 反向编目 wizard 非占位.

前置：本 worktree 已 `npm run build`（zw-brain-web/dist-vite），且 REST 指向同一份
dist（`bash scripts/start-local.sh` 或指定端口）：

  ZW_BRAIN_REST_PORT=8801 bash scripts/start-local.sh   # 8800 被占用时

Run:
  .venv/bin/python3 tests/e2e/wave1_j2_provider_p5_smoke.py
  ZW_E2E_BASE_URL=http://127.0.0.1:8801 .venv/bin/python3 tests/e2e/wave1_j2_provider_p5_smoke.py

Exit 0 = 全部子页不含「功能建设中」；2 = /health 不可达；1 = 断言失败。
"""
from __future__ import annotations

import json
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.e2e.conftest import CONFIG  # noqa: E402

SMOKE_DIR = CONFIG.screenshot_dir.parents[1] / "wave1" / "screenshots" / "provider-p5-smoke"
PLACEHOLDER_MARK = "功能建设中"

ROUTES: tuple[tuple[str, str], ...] = (
    ("#/provider/inbox/field-decision", "反向编目审核收件箱"),
    ("#/provider/inbox/hookup-review", "挂接审核收件箱"),
    ("#/provider/inbox/demand-match", "供需对接收件箱"),
    ("#/provider/inbox/objection", "异议响应收件箱"),
    ("#/provider/wizard/reverse-catalog", "反向编目"),
)

STEPS: list[dict] = []


def _log(step: str, expected: str, actual: str, ok: bool) -> None:
    mark = "PASS" if ok else "FAIL"
    STEPS.append({"step": step, "expected": expected, "actual": actual, "ok": ok})
    print(f"[{mark}] {step}\n      expect: {expected}\n      actual: {actual}", flush=True)


def _server_reachable() -> bool:
    health_url = CONFIG.base_url.rstrip("/") + "/health"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(health_url, timeout=3) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _wait_app_ready(page) -> None:
    page.wait_for_selector(".user-menu-button", state="visible", timeout=CONFIG.nav_timeout_ms)
    page.wait_for_selector("#role-switch", state="visible", timeout=CONFIG.nav_timeout_ms)


def _set_role(page, role: str) -> None:
    page.select_option("#role-switch", role)
    page.wait_for_timeout(1200)


def _goto_hash(page, hash_value: str) -> None:
    page.evaluate("h => { window.location.hash = h; }", hash_value)
    page.wait_for_timeout(800)


def run() -> int:
    if not _server_reachable():
        print(
            f"[SKIP] {CONFIG.base_url}/health 不可达 — 请先在本 worktree 启动 REST（dist-vite 需已 build）",
            flush=True,
        )
        return 2

    CONFIG.ensure_dirs()
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
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
            _wait_app_ready(page)
            who = page.locator(".user-menu-button").inner_text()
            _log(
                "bootstrap-auth",
                "dev IAM bypass 已登录且岗位切换可见",
                f"user={who!r}",
                bool(who.strip()),
            )
            if not who.strip():
                failed = True

            _set_role(page, "ROLE_ORGAN_MANAGER")

            for idx, (hash_route, label) in enumerate(ROUTES, start=1):
                _goto_hash(page, hash_route)
                page.wait_for_selector("#app-router", timeout=CONFIG.nav_timeout_ms)
                page.wait_for_timeout(600)
                txt = page.locator("#app-router").inner_text()
                ok = PLACEHOLDER_MARK not in txt and label in txt
                shot = SMOKE_DIR / f"{idx:02d}-{hash_route.strip('#/').replace('/', '-')}.png"
                page.screenshot(path=str(shot), full_page=True)
                _log(
                    f"Step{idx} MANAGER {label}",
                    f"不含「{PLACEHOLDER_MARK}」且渲染 {label}",
                    f"placeholder={PLACEHOLDER_MARK in txt}, has_label={label in txt}, screenshot={shot}",
                    ok,
                )
                if not ok:
                    failed = True

        except Exception as exc:  # noqa: BLE001
            failed = True
            _log("UNCAUGHT", "no exception", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", False)
        finally:
            (SMOKE_DIR / "summary.json").write_text(
                json.dumps({"routes": ROUTES, "steps": STEPS}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            context.close()
            browser.close()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
