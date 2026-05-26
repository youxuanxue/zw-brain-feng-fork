#!/usr/bin/env python3
"""逐页浏览验收 — 视觉/数据/逻辑冒烟（本地 start-local + dist-vite 已 build）."""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8822"
OUT = REPO / ".data" / "jobs-page-audit"
PLACEHOLDER = "功能建设中"
BAD_TERMS = ("capability", "projection", "package", "write-with-audit", "pendingBackend", "E2 ", "E5 ", "E6 ")
EN_LEAK = re.compile(r"\b(pending|approved|rejected|issued|active|draft|live|mock)\b", re.I)

# (hash, role, label, expect_table_or_detail)
PAGES: list[tuple[str, str, str, str]] = [
    ("#/workbench", "ROLE_ORGAN_OPERATER", "P1 工作台", "any"),
    ("#/discovery", "ROLE_ORGAN_OPERATER", "P2 资源发现", "any"),
    ("#/request-flow", "ROLE_ORGAN_OPERATER", "P3 申请审批", "any"),
    ("#/delivery-exchange", "ROLE_ORGAN_OPERATER", "P4 交付交换", "any"),
    ("#/zones-pack", "ROLE_ORGAN_OPERATER", "P7 共享专区", "any"),
    ("#/provider", "ROLE_ORGAN_MANAGER", "P5 提供方管理", "cards"),
    ("#/provider/wizard/reverse-catalog", "ROLE_ORGAN_MANAGER", "P5 反向编目向导", "form"),
    ("#/provider/wizard/api-service", "ROLE_ORGAN_MANAGER", "P5 API服务化向导", "form"),
    ("#/provider/wizard/quality-rule", "ROLE_ORGAN_MANAGER", "P5 质量规则向导", "form"),
    ("#/provider/inbox/field-decision", "ROLE_ORGAN_MANAGER", "P5 字段裁决收件箱", "table_or_empty"),
    ("#/provider/inbox/hookup-review", "ROLE_ORGAN_MANAGER", "P5 挂接审核收件箱", "table_or_empty"),
    ("#/provider/inbox/demand-match", "ROLE_ORGAN_MANAGER", "P5 供需对接收件箱", "table_or_empty"),
    ("#/provider/inbox/objection", "ROLE_ORGAN_MANAGER", "P5 异议响应收件箱", "table_or_empty"),
    ("#/compliance-ops", "ROLE_SECURITY_AUDIT", "B1.1 合规运营", "any"),
    ("#/integration-admin", "ROLE_BUSIAUDIT", "B1.2 接入中心", "any"),
    ("#/integration-admin/iam-governance", "ROLE_BUSIAUDIT", "B1.2 身份治理", "table_or_empty"),
    ("#/integration-admin/engines", "ROLE_SYSTEM", "B1.2 三引擎子页", "any"),
]

issues: list[dict] = []


def fetch_snapshot(role: str) -> dict:
    url = f"{BASE}/api/snapshot?role={role}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def audit_page(page, hash_route: str, role: str, label: str, expect: str) -> None:
    page.select_option("#role-switch", role)
    page.wait_for_timeout(900)
    page.evaluate("h => { window.location.hash = h; }", hash_route)
    page.wait_for_timeout(900)
    page.wait_for_selector("#app-router", timeout=15000)
    txt = page.locator("#app-router").inner_text()
    slug = hash_route.strip("#/").replace("/", "-") or "root"
    shot = OUT / "screenshots" / f"{slug}.png"
    page.screenshot(path=str(shot), full_page=True)

    if PLACEHOLDER in txt:
        issues.append({"page": label, "kind": "placeholder", "detail": PLACEHOLDER})
    for term in BAD_TERMS:
        if term.lower() in txt.lower():
            issues.append({"page": label, "kind": "engineering-term", "detail": term})
    if EN_LEAK.search(txt):
        m = EN_LEAK.search(txt)
        issues.append({"page": label, "kind": "en-leak", "detail": m.group(0) if m else ""})
    if "等待数据装载" in txt and "正在加载" not in txt:
        issues.append({"page": label, "kind": "stuck-loading", "detail": "等待数据装载"})
    if "兜底回退" in txt or "NL 后端等" in txt:
        issues.append({"page": label, "kind": "nl-fallback", "detail": "NL 仍走 fixture 兜底"})
    if expect == "table_or_empty" and "focus-table" not in page.content() and "暂无" not in txt:
        issues.append({"page": label, "kind": "inbox-empty-copy", "detail": "无表格也无「暂无」提示"})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "screenshots").mkdir(exist_ok=True)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{BASE}/health", timeout=3) as r:
            if r.status != 200:
                print(f"FAIL health {r.status}")
                return 2
    except OSError as e:
        print(f"FAIL server unreachable: {e}")
        return 2

    snap_mgr = fetch_snapshot("ROLE_ORGAN_MANAGER")
    provider = (snap_mgr.get("provider") or {})
    print(f"snapshot provider counts: field={len(provider.get('field_decisions') or [])} "
          f"hookup={len(provider.get('hookup_reviews') or [])} "
          f"demand={len(provider.get('demand_matches') or [])} "
          f"objection={len(provider.get('objection_cases') or [])}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-proxy-server"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector("#role-switch", timeout=30000)

        for hash_route, role, label, expect in PAGES:
            print(f"audit {label} …")
            try:
                audit_page(page, hash_route, role, label, expect)
            except Exception as exc:  # noqa: BLE001
                issues.append({"page": label, "kind": "exception", "detail": str(exc)})

        # P3 审批写路径：MANAGER 点进第一条审批
        page.select_option("#role-switch", "ROLE_ORGAN_MANAGER")
        page.wait_for_timeout(900)
        page.evaluate("() => { window.location.hash = '#/request-flow'; }")
        page.wait_for_timeout(1200)
        review_link = page.locator('a[href*="#/request-flow/review/"]').first
        if review_link.count():
            review_link.click()
            page.wait_for_timeout(1200)
            approve_btn = page.get_by_role("button", name=re.compile("通过|批准|同意"))
            if approve_btn.count() == 0:
                issues.append({"page": "P3 审批详情", "kind": "logic", "detail": "无审批通过按钮"})
        else:
            issues.append({"page": "P3 申请审批", "kind": "data", "detail": "MANAGER 视图无待审链接"})

        # P4 凭据 issued 应显示已签发
        page.select_option("#role-switch", "ROLE_ORGAN_OPERATER")
        page.wait_for_timeout(900)
        page.evaluate("() => { window.location.hash = '#/delivery-exchange'; }")
        page.wait_for_timeout(1200)
        p4 = page.locator("#app-router").inner_text()
        if "待处理" in p4 and "已签发" in p4:
            issues.append({"page": "P4 交付", "kind": "logic", "detail": "issued 与待处理混显"})
        if re.search(r"\bissued\b", p4, re.I):
            issues.append({"page": "P4 交付", "kind": "en-leak", "detail": "issued 裸枚举"})

        ctx.close()
        browser.close()

    report = {"base": BASE, "issues": issues, "pages": len(PAGES)}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
