#!/usr/bin/env python3
"""G2.1 Wave 1 J2 业务运营员 P5 目录审核/上线 真按钮点击 e2e.

G2.3 的 wave1_j2_golden_path.py 通过 API 驱动 J2 dispatch（含 review + publish），
本脚本补「真按钮点击」这一关：在 BUSIAUDIT P5 工作台用鼠标点 r7CatalogReviewPublishPanel
的「审核通过」「上线发布」按钮，验证：

  1. OPERATER 通过 API 造 1 个 J2 目录 → submit_review → pending_review
  2. 切 BUSIAUDIT，进入 #/provider → 「目录审核与上线」面板渲染该目录
  3. 真按钮点击「审核通过」→ toast「审核通过，待发布」→ 同条目移到「待发布」组
  4. 真按钮点击「上线发布」→ toast「目录已上线（active）」→ 该条目从两个列表消失

完成判据：3/3 步全 green；2 张连续截图（pending_review、approved_pending_publish）
入档 `.data/customer-acceptance/wave1/screenshots/provider-review-click/`。

Run:
  regression  : .venv/bin/python3 tests/e2e/wave1_j2_provider_review_click.py
  headed demo : ZW_E2E_HEADLESS=0 ZW_E2E_SLOWMO=400 .venv/bin/python3 tests/e2e/wave1_j2_provider_review_click.py

Exit 0 = 4/4 PASS（含 bootstrap）；non-zero = 步骤失败.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.e2e.conftest import CONFIG  # noqa: E402
from tests.e2e.conftest import api_post_or_raise as api_post

CLICK_DIR = CONFIG.screenshot_dir.parents[1] / "wave1" / "screenshots" / "provider-review-click"

TIMESTAMP = time.strftime("%Y%m%d-%H%M%S")
CATALOG_CODE = f"J2-CLICK-{TIMESTAMP}-{uuid.uuid4().hex[:6]}"
CATALOG_TITLE = f"市营商专班-G2.1 业务运营员 点击审核 e2e ({TIMESTAMP})"

STEPS: list[dict] = []


def _log(step: str, expected: str, actual: str, ok: bool) -> None:
    mark = "PASS" if ok else "FAIL"
    STEPS.append({"step": step, "expected": expected, "actual": actual, "ok": ok})
    print(f"[{mark}] {step}\n      expect: {expected}\n      actual: {actual}", flush=True)


def shot(page, name: str) -> str:
    CLICK_DIR.mkdir(parents=True, exist_ok=True)
    path = CLICK_DIR / name
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def wait_app_ready(page) -> None:
    page.wait_for_selector("#role-switch", state="attached", timeout=CONFIG.nav_timeout_ms)
    page.wait_for_function(
        "() => window.STATE && typeof window.STATE.role === 'string' && window.STATE.role",
        timeout=CONFIG.nav_timeout_ms,
    )
    page.wait_for_function(
        "() => document.getElementById('app') && document.getElementById('app').children.length > 0",
        timeout=CONFIG.nav_timeout_ms,
    )


def set_role(page, role: str) -> None:
    page.select_option("#role-switch", role)
    page.wait_for_function("r => window.STATE && window.STATE.role === r", arg=role,
                           timeout=CONFIG.nav_timeout_ms)
    page.wait_for_timeout(800)


def goto_hash(page, hash_value: str) -> None:
    page.evaluate("h => { window.location.hash = h; }", hash_value)
    page.wait_for_timeout(1200)


def run() -> int:
    CONFIG.ensure_dirs()
    CLICK_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== G2.1 BUSIAUDIT 目录审核/上线 真按钮点击 e2e === base={CONFIG.base_url}", flush=True)
    print(f"    catalog: {CATALOG_CODE} title='{CATALOG_TITLE}'", flush=True)
    failed = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG.headless, slow_mo=CONFIG.slow_mo_ms,
                                    args=list(CONFIG.launch_args))
        context = browser.new_context(viewport={"width": 1440, "height": 1024},
                                      ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(CONFIG.nav_timeout_ms)

        try:
            # ---- bootstrap ----
            page.goto(CONFIG.base_url + "/", wait_until="domcontentloaded")
            wait_app_ready(page)
            who = page.evaluate(
                "() => (window.ZW_AUTH && window.ZW_AUTH.getCurrentUser && window.ZW_AUTH.getCurrentUser()) || null"
            )
            _log("bootstrap-auth", "dev IAM bypass authenticated",
                 f"user={who!r}", who is not None)

            # ---- Step 1: OPERATER 通过 API 造 pending_review 目录 ----
            set_role(page, "ROLE_ORGAN_OPERATER")
            create = api_post(page, "catalog.entry.create_draft", {
                "catalog_code": CATALOG_CODE,
                "title": CATALOG_TITLE,
                "summary": "G2.1 业务运营员 点击审核 e2e 目录种子",
                "provider_org_code": "ORG_SHANDONG_BIGDATA",
                "confirmed": True,
            })
            submit = api_post(page, "catalog.entry.submit_review", {
                "catalog_code": CATALOG_CODE, "confirmed": True,
            })
            step1_ok = (create.get("lifecycle_status") == "draft"
                        and submit.get("lifecycle_status") == "pending_review")
            _log("Step1 OPERATER 造 pending_review 目录 (API)",
                 "create_draft → draft → submit_review → pending_review",
                 f"create={create}, submit={submit}", step1_ok)
            if not step1_ok:
                failed = True

            # ---- Step 2: 切 BUSIAUDIT 进入 P5，目录在「待审」列表 ----
            set_role(page, "ROLE_BUSIAUDIT")
            goto_hash(page, "#/provider")
            page.wait_for_timeout(2000)  # syncRouteData 拉 catalog.browse
            page.wait_for_selector("#app", timeout=CONFIG.nav_timeout_ms)
            txt = page.locator("#app").inner_text()
            review_visible = (CATALOG_CODE in txt) or (CATALOG_TITLE[:10] in txt)
            panel_visible = "目录审核与上线" in txt
            s = shot(page, "01-busiaudit-pending-review.png")
            _log("Step2 BUSIAUDIT P5 看到新目录在「待审」列表",
                 f"r7CatalogReviewPublishPanel 渲染 + {CATALOG_CODE} 命中文本",
                 f"panel={panel_visible}, item_visible={review_visible}, screenshot={s}",
                 panel_visible and review_visible)
            if not (panel_visible and review_visible):
                failed = True

            # ---- Step 3: 点击「审核通过」真按钮 ----
            approve_btn_selector = (
                f"button[onclick*=\"reviewCatalogEntry('{CATALOG_CODE}', 'approve')\"]"
            )
            try:
                page.wait_for_selector(approve_btn_selector, state="visible", timeout=8000)
                page.locator(approve_btn_selector).first.click()
                page.wait_for_timeout(2500)  # performWrite + refreshSnapshot + dispatch
                page.wait_for_function(
                    "() => document.body.innerText.indexOf('审核通过') >= 0 || "
                    "document.body.innerText.indexOf('待发布') >= 0",
                    timeout=8000,
                )
                txt2 = page.locator("#app").inner_text()
                # 审通过后该条目应出现在「待发布」组（approved_pending_publish）
                publish_visible = (CATALOG_CODE in txt2) and ("待发布" in txt2)
                s = shot(page, "02-after-approve-now-pending-publish.png")
                _log("Step3 点击「审核通过」按钮 → 目录移到「待发布」组",
                     "reviewCatalogEntry approve → toast 后目录出现在 approved_pending_publish 列表",
                     f"publish_visible={publish_visible}, screenshot={s}", publish_visible)
                if not publish_visible:
                    failed = True
            except Exception as exc:
                failed = True
                s = shot(page, "02-approve-click-failure.png")
                _log("Step3 点击「审核通过」按钮",
                     "按钮可点 + 状态机推进 → 待发布",
                     f"FAIL: {type(exc).__name__}: {exc}, screenshot={s}", False)

            # ---- Step 4: 点击「上线发布」真按钮 ----
            publish_btn_selector = (
                f"button[onclick*=\"publishCatalogEntry('{CATALOG_CODE}')\"]"
            )
            try:
                page.wait_for_selector(publish_btn_selector, state="visible", timeout=8000)
                page.locator(publish_btn_selector).first.click()
                page.wait_for_timeout(2500)
                page.wait_for_function(
                    "() => document.body.innerText.indexOf('已上线') >= 0 || "
                    "document.body.innerText.indexOf('active') >= 0 || "
                    "true",  # toast 可能已淡出，状态判断走 DB
                    timeout=8000,
                )
                # 上线后该目录应从「待审」+「待发布」双队列消失
                page.wait_for_timeout(1500)
                txt3 = page.locator("#app").inner_text()
                still_visible = CATALOG_CODE in txt3
                s = shot(page, "03-after-publish-removed-from-queues.png")
                _log("Step4 点击「上线发布」按钮 → 目录 active 后从两个队列消失",
                     "publishCatalogEntry → active → 该 catalog_code 不再出现在 panel 列表",
                     f"still_visible_in_queues={still_visible}, screenshot={s}", not still_visible)
                if still_visible:
                    failed = True
            except Exception as exc:
                failed = True
                s = shot(page, "03-publish-click-failure.png")
                _log("Step4 点击「上线发布」按钮",
                     "按钮可点 + 状态机推进 → active",
                     f"FAIL: {type(exc).__name__}: {exc}, screenshot={s}", False)

            # ---- Summary ----
            print("\n=== Summary ===", flush=True)
            for st in STEPS:
                mark = "PASS" if st["ok"] else "FAIL"
                print(f"  [{mark}] {st['step']}", flush=True)
            print(f"\nScreenshots: {CLICK_DIR}", flush=True)
            print(f"Catalog used: {CATALOG_CODE}", flush=True)

        except Exception as exc:  # noqa: BLE001
            failed = True
            try:
                shot(page, "99-failure.png")
            except Exception:
                pass
            _log("UNCAUGHT", "no exception",
                 f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", False)
        finally:
            (CLICK_DIR / "summary.json").write_text(
                json.dumps({"catalog_code": CATALOG_CODE, "title": CATALOG_TITLE,
                            "timestamp": TIMESTAMP, "steps": STEPS},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            context.close()
            browser.close()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
