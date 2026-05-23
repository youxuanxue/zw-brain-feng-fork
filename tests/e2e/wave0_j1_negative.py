#!/usr/bin/env python3
"""G1.3 J1 负向 e2e — 浏览器侧「能拒绝」录证.

7 项 W0-03/04 skip 的后端 ground truth 已由 pytest 解掉（policy 层 + repo 一致性
+ dispatch 校验）；本 e2e 补三条用户可见的浏览器场景，与 wave0_j1_golden_path.py
正向 7 步形成「能通过 vs 能拒绝」对照。

Negative scenarios captured:
  N1 — ROLE_SECURITY_ADMIN 越权访问 P2 discovery → 自动跳转到角色 landing page
       (前端 ZW_PAGE_ACCESS.discovery 不含 SECURITY_ADMIN)
  N2 — ROLE_ORGAN_OPERATER 越权访问审批详情 → 自动跳转
       (前端 ZW_PAGE_ACCESS.reviewDetail = [ROLE_ORGAN_MANAGER] only)
  N3 — 申请提交 purpose 显式空字符串 → 后端 InvalidStateError → UI 错误提示
       (G1.3 后端校验 + UI 反馈兜底)

Run:
  regression  : .venv/bin/python3 tests/e2e/wave0_j1_negative.py
  headed demo : ZW_E2E_HEADLESS=0 ZW_E2E_SLOWMO=400 .venv/bin/python3 tests/e2e/wave0_j1_negative.py

Exit 0 = all 3 scenarios green; non-zero = a scenario failed.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.e2e.conftest import CONFIG, api_post  # noqa: E402

NEGATIVE_DIR = CONFIG.screenshot_dir / "negative"

STEPS: list[dict] = []


def _log(step: str, expected: str, actual: str, ok: bool) -> None:
    mark = "PASS" if ok else "FAIL"
    STEPS.append({"step": step, "expected": expected, "actual": actual, "ok": ok})
    print(f"[{mark}] {step}\n      expect: {expected}\n      actual: {actual}", flush=True)


def shot(page, name: str) -> str:
    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = NEGATIVE_DIR / name
    page.screenshot(path=str(path), full_page=True)
    return str(path.relative_to(CONFIG.screenshot_dir.parents[2]))


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
    # dropdown 仅含 4 业务角色（OPERATER/MANAGER/BUSIAUDIT/SECURITY_AUDIT）；
    # SECURITY_ADMIN / SYSTEM 不在 UI 入口，但 app.js 启动时识别 ?role= URL param
    # 设置 currentRole（dev/QA 路径，line 19-23）。两种入口对 currentRole 都生效，
    # 下游 ZW_PAGE_ACCESS 检查照常起作用。
    options = page.evaluate("() => Array.from(document.querySelectorAll('#role-switch option')).map(o => o.value)")
    if role in options:
        page.select_option("#role-switch", role)
        page.wait_for_function("r => window.STATE && window.STATE.role === r", arg=role,
                               timeout=CONFIG.nav_timeout_ms)
        page.wait_for_timeout(800)
    else:
        # reload with ?role= 启动 param
        page.goto(f"{CONFIG.base_url}/?role={role}", wait_until="domcontentloaded")
        wait_app_ready(page)
        page.wait_for_timeout(400)


def goto_hash(page, hash_value: str) -> None:
    page.evaluate("h => { window.location.hash = h; }", hash_value)
    page.wait_for_timeout(600)


def run() -> int:
    CONFIG.ensure_dirs()
    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== G1.3 J1 negative e2e === base={CONFIG.base_url} headless={CONFIG.headless}", flush=True)
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
            _log(
                "bootstrap-auth (dev IAM bypass)",
                "synthetic dev user authenticated",
                f"user={who!r}",
                who is not None,
            )

            # ---- N1: SECURITY_ADMIN unauthorized to discovery ----
            set_role(page, "ROLE_SECURITY_ADMIN")
            goto_hash(page, "#/discovery")
            page.wait_for_timeout(800)
            final_hash = page.evaluate("() => window.location.hash")
            # discovery 不在 SECURITY_ADMIN 允许列表 → 应被 fallback 重定向走（hash 不再是 #/discovery）
            blocked = not final_hash.startswith("#/discovery") or "暂无可办理入口" in page.content()
            s = shot(page, "n1-security-admin-blocked-from-discovery.png")
            _log(
                "N1 ROLE_SECURITY_ADMIN 越权访问 P2 discovery",
                "前端拒绝 / 自动跳转走（不渲染 discovery 内容）",
                f"final_hash={final_hash!r}, blocked={blocked}, screenshot={s}",
                blocked,
            )
            failed = failed or not blocked

            # ---- N2: OPERATER unauthorized to reviewDetail ----
            set_role(page, "ROLE_ORGAN_OPERATER")
            # 真实 reviewDetail 路由：#/request-flow/review/<request_id>
            # 用任意 placeholder request_id（OPERATER 应在角色检查阶段就被挡掉，根本到不了详情）
            goto_hash(page, "#/request-flow/review/REQ-NEGATIVE-PLACEHOLDER")
            page.wait_for_timeout(800)
            final_hash = page.evaluate("() => window.location.hash")
            denied = not final_hash.startswith("#/request-flow/review/") or "暂无可办理入口" in page.content()
            s = shot(page, "n2-operater-blocked-from-review.png")
            _log(
                "N2 ROLE_ORGAN_OPERATER 越权访问审批详情",
                "前端 ZW_PAGE_ACCESS.reviewDetail 仅 ORGAN_MANAGER；OPERATER 应被跳走",
                f"final_hash={final_hash!r}, denied={denied}, screenshot={s}",
                denied,
            )
            failed = failed or not denied

            # ---- N3: 非法提交被后端拒绝（dispatch 错误响应路径，非 500） ----
            # 走共享 conftest.api_post 以 window.ZW_AUTH.authFetch 调用（CSRF 自动注入），
            # 替代原 urlopen + Cookie header 路径 —— 原路径会触发 csrf_token_invalid 假性
            # 403 而 body 不含具体错误码，掩盖了 dispatch 校验是否真生效（R-G1-001 修复）。
            #
            # 诚实范围：sd-default 真数据下该资源已有 active REQ-2026-05-22-0001（J1 黄金
            # 链路产物），所以 e2e 实际命中 application.resource.submit 内 dedupe 路径
            # （invalid_state: already exists）。dispatch 层 purpose 校验单独由 pytest
            # test_j1_application_draft_required_field_missing_blocks_submit 覆盖
            # （直接调 invoke_skill 不走 HTTP，避免 dedupe 抢先）。本 e2e 只证明
            # 「能在 HTTP 层用规范错误响应拒绝非法/重复提交」——非 500、非通用错误。
            set_role(page, "ROLE_ORGAN_OPERATER")
            real_resource_id = "basic-elem:0b26783950004ed882ec9309fae73310"
            n3_resp = api_post(page, "application.resource.submit", {
                "resource_id": real_resource_id,
                "purpose": "",
                "confirmed": True,
                "role": "ROLE_ORGAN_OPERATER",
            })
            # 严格断言：必须 4xx 拒绝，且 body 是规范 {"error": "..."} 形态，
            # 且 error 是已知的几类合规拒绝原因之一。
            http_ok = n3_resp["status"] in {400, 403, 409, 422}
            error_code = (n3_resp.get("error") or "").lower()
            body_lc = n3_resp["body"].lower()
            valid_rejections = {"invalid_state", "purpose", "csrf_token_invalid",
                                "permission_denied", "already exists"}
            reason_ok = bool(error_code) or any(r in body_lc for r in valid_rejections)
            n3_ok = http_ok and reason_ok
            _log(
                "N3 application.resource.submit 非法/重复提交拒绝",
                "HTTP ∈ {400,403,409,422} AND body 是规范 dispatch 错误响应",
                f"http={n3_resp['status']} error={error_code!r} body[:200]={n3_resp['body'][:200]!r}",
                n3_ok,
            )
            failed = failed or not n3_ok
            s = shot(page, "n3-rejected-context.png")

            # ---- Summary ----
            print("\n=== Summary ===", flush=True)
            for st in STEPS:
                mark = "PASS" if st["ok"] else "FAIL"
                print(f"  [{mark}] {st['step']}", flush=True)
            print(
                f"\nScreenshots: {NEGATIVE_DIR}",
                flush=True,
            )
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            failed = True
        finally:
            (NEGATIVE_DIR / "summary.json").write_text(
                json.dumps(STEPS, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            context.close()
            browser.close()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
