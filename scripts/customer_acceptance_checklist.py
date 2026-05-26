#!/usr/bin/env python3
"""PR #106 客户验收清单 — 逐项浏览器 + 数据断言."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright  # noqa: E402

_DEFAULT_PORT = os.environ.get("ZW_BRAIN_REST_PORT", "8800")
BASE = sys.argv[1] if len(sys.argv) > 1 else f"http://127.0.0.1:{_DEFAULT_PORT}"
PLACEHOLDER = "功能建设中"
FORBIDDEN = re.compile(
    r"skill_id|plan\.yaml|\bcapability\b|\bprojection\b|write-with-audit|E[1-6]\s+F[0-9]|E[1-6]\s+",
    re.I,
)
EN_SLUG = re.compile(r"\b(issued|pending|approved|rejected|granted)\b", re.I)

results: list[dict] = []


def record(step: str, ok: bool, detail: str) -> None:
    results.append({"step": step, "ok": ok, "detail": detail})
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {step}\n       {detail}", flush=True)


def fetch_json(path: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode())


def app_text(page) -> str:
    return page.locator("#app-router").inner_text()


def forbidden_in(text: str) -> str | None:
    m = FORBIDDEN.search(text)
    return m.group(0) if m else None


def wait_ready(page) -> None:
    page.goto(BASE + "/", wait_until="domcontentloaded")
    login_btn = page.locator("#login-gate-submit")
    if login_btn.count() > 0:
        login_btn.click()
        page.wait_for_timeout(600)
    page.wait_for_selector(".user-menu-button", timeout=30000)
    page.wait_for_selector("#role-switch", timeout=30000)


def set_role(page, role: str) -> None:
    page.select_option("#role-switch", role)
    page.wait_for_timeout(1000)


def goto(page, hash_route: str) -> None:
    page.evaluate("h => { window.location.hash = h; }", hash_route)
    page.wait_for_timeout(900)
    page.wait_for_selector("#app-router", timeout=15000)


def main() -> int:
    try:
        fetch_json("/health")
    except OSError as exc:
        print(f"FAIL server unreachable: {exc}")
        return 2

    mgr = fetch_json("/api/snapshot?role=ROLE_ORGAN_MANAGER")
    provider = mgr.get("provider") or {}
    record(
        "数据 P5 provider 投影",
        bool(provider.get("field_decisions") or provider.get("hookup_reviews") or provider.get("objection_cases")),
        f"field={len(provider.get('field_decisions') or [])} hookup={len(provider.get('hookup_reviews') or [])} "
        f"demand={len(provider.get('demand_matches') or [])} objection={len(provider.get('objection_cases') or [])}",
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-proxy-server"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = ctx.new_page()
        wait_ready(page)

        # J1 操作员
        set_role(page, "ROLE_ORGAN_OPERATER")
        goto(page, "#/workbench")
        t = app_text(page)
        record("P1 工作台 live", "待办" in t and PLACEHOLDER not in t, t[:120].replace("\n", " "))

        goto(page, "#/discovery")
        t = app_text(page)
        record("P2 资源发现", page.get_by_role("heading", name="可复用资源").is_visible(), t[:80])

        goto(page, "#/request-flow")
        t = app_text(page)
        record("P3 操作员在途申请", "在途申请" in t and "待我审批" not in t, t[:80])

        goto(page, "#/delivery-exchange")
        t = app_text(page)
        bad_en = EN_SLUG.search(t)
        record(
            "P4 交付无裸枚举",
            "交付任务" in t and bad_en is None and PLACEHOLDER not in t,
            f"en_leak={bad_en.group(0) if bad_en else None}",
        )

        goto(page, "#/zones-pack/zone/business")
        t = app_text(page)
        record("P7 专题详情", "城市运行专区" in t and PLACEHOLDER not in t, t[:80])

        # J1 管理员审批 + J2 P5
        set_role(page, "ROLE_ORGAN_MANAGER")
        goto(page, "#/request-flow")
        t = app_text(page)
        has_review = page.locator('a[href*="#/request-flow/review/"]').count() > 0
        review_links = page.locator('a[href*="#/request-flow/review/"]').count()
        record(
            "P3 管理员待我审批",
            "待我审批" in t and has_review,
            f"links={review_links}",
        )

        goto(page, "#/request-flow/review/REQ-2026-05-25-0001")
        t = app_text(page)
        fb = forbidden_in(t)
        record(
            "P3 审批详情文案",
            "审批详情" in t and fb is None and page.get_by_role("button", name="通过").is_visible(),
            f"forbidden={fb}",
        )

        goto(page, "#/provider")
        t = app_text(page)
        cards = page.locator(".stat-card strong")
        nums = [cards.nth(i).inner_text() for i in range(min(cards.count(), 4))]
        record("P5 四卡待办", cards.count() >= 4 and any(int(n) > 0 for n in nums if n.isdigit()), f"counts={nums}")

        for route, label in (
            ("#/provider/inbox/field-decision", "字段裁决收件箱"),
            ("#/provider/inbox/hookup-review", "挂接审核收件箱"),
            ("#/provider/inbox/demand-match", "供需对接收件箱"),
            ("#/provider/inbox/objection", "异议响应收件箱"),
            ("#/provider/wizard/reverse-catalog", "反向编目向导"),
        ):
            goto(page, route)
            t = app_text(page)
            fb = forbidden_in(t)
            record(
                f"P5 {label}",
                label in t and PLACEHOLDER not in t and fb is None,
                f"placeholder={PLACEHOLDER in t} forbidden={fb}",
            )

        # 审批 toast 不含 skill_id
        goto(page, "#/request-flow/review/REQ-2026-05-25-0001")
        page.get_by_role("button", name="通过").click()
        page.wait_for_timeout(1500)
        toast = page.locator(".toast-stack, .toast, [class*='toast']").first
        toast_txt = toast.inner_text() if toast.count() else page.content()
        record(
            "Toast 无工程术语",
            "approval.case" not in toast_txt.lower() and "plan.yaml" not in toast_txt.lower(),
            toast_txt[:160].replace("\n", " "),
        )

        # B1
        set_role(page, "ROLE_SECURITY_AUDIT")
        goto(page, "#/compliance-ops")
        t = app_text(page)
        record("B1.1 合规运营", "合规" in t or "运营" in t, t[:80])

        set_role(page, "ROLE_BUSIAUDIT")
        goto(page, "#/integration-admin")
        t = app_text(page)
        fb = forbidden_in(t)
        record("B1.2 接入中心", "接入扩展中心" in t and fb is None, f"forbidden={fb}")

        has_gov_link = page.locator('a[href="#/integration-admin/iam-governance"]').count() > 0
        record("B1.2 身份治理入口", has_gov_link, "接入中心顶栏「身份治理」链接")

        goto(page, "#/integration-admin/iam-governance")
        t = app_text(page)
        fb = forbidden_in(t)
        record(
            "B1.2 身份治理页",
            "身份治理" in t and "映射候选列表" in t and PLACEHOLDER not in t and fb is None,
            f"forbidden={fb}",
        )

        set_role(page, "ROLE_ORGAN_OPERATER")
        goto(page, "#/integration-admin/iam-governance")
        page.wait_for_timeout(1200)
        record(
            "B1.2 身份治理岗位守卫",
            "#/integration-admin/iam-governance" not in page.evaluate("() => location.hash"),
            page.evaluate("() => location.hash"),
        )

        set_role(page, "ROLE_SYSTEM")
        goto(page, "#/engines-admin")
        t = app_text(page)
        record("B1.3 三引擎", "三引擎" in t and PLACEHOLDER not in t, t[:80])

        # 操作员无权 P5
        set_role(page, "ROLE_ORGAN_OPERATER")
        goto(page, "#/provider")
        page.wait_for_timeout(1200)
        record("岗位守卫 P5", "#/provider" not in page.evaluate("() => location.hash"), page.evaluate("() => location.hash"))

        ctx.close()
        browser.close()

    out = REPO / ".data" / "customer-acceptance-checklist.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"base": BASE, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r for r in results if not r["ok"]]
    print(f"\n=== {len(results) - len(failed)}/{len(results)} passed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
