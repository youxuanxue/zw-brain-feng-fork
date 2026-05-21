#!/usr/bin/env python3
"""自动化捕获 J1+J2+J3 5 张关键截图（CDP via headless Chrome）.

复用 tests/test_webui_browser_e2e.py 的 BrowserE2E + _open_browser 基础设施。
输出到 docs/release-notes/j1j2j3-loop-2026-05-19/ 目录。

用法：
    .venv/bin/python scripts/capture_j1j2j3_screenshots.py

预置条件：
- macOS Chrome 已安装
- venv 已装；schema 由 ensure_runtime_schema 自动建（v4.1 R15：不用 alembic）
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Bypass envvars 必须先于 import
os.environ["ZW_BRAIN_DEV_IAM_BYPASS"] = "1"
os.environ["ZW_BRAIN_DEV_IAM_BYPASS_ACK"] = "development-only"
os.environ["ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH"] = "1"

from tests.test_webui_browser_e2e import (  # noqa: E402 — bypass env vars must precede import
    _open_browser,
    _set_role,
    _start_rest_server,
    _wait_for,
)
from zw_brain.command.runtime import reset_service  # noqa: E402 — same reason

OUTPUT_DIR = REPO / "docs" / "release-notes" / "j1j2j3-loop-2026-05-19"


def screenshot(browser, path: Path, *, viewport_height: int = 900) -> None:
    """截图并保存到指定路径."""
    # 设置 viewport 大小
    browser.send("Emulation.setDeviceMetricsOverride", {
        "width": 1440,
        "height": viewport_height,
        "deviceScaleFactor": 2,
        "mobile": False,
    })
    result = browser.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = base64.b64decode(result["data"])
    path.write_bytes(data)
    print(f"  saved → {path.relative_to(REPO)} ({len(data) // 1024} KB)")


def capture_01_j1_credential(base_url: str) -> None:
    print("01 - J1 凭据领取页（P4 已签发凭据 + curl 示例）")
    browser = _open_browser(f"{base_url}/#/delivery-exchange/credential/REQ-2026-04-26-0006")
    try:
        _wait_for(browser, "document.body && document.body.innerText.length > 100", timeout=10)
        time.sleep(1)  # 给渲染留时间
        screenshot(browser, OUTPUT_DIR / "01-j1-credential.png", viewport_height=1400)
    finally:
        browser.close()


def capture_02_sharing_type(base_url: str) -> None:
    print("02 - J1 sharing_type 分流 UI（reviewDetail）")
    browser = _open_browser(f"{base_url}/#/request-flow/review/REQ-2026-04-25-0011")
    try:
        _wait_for(browser, "document.body && document.body.innerText.length > 200", timeout=10)
        _wait_for(browser, "document.getElementById('role-switch') && window.STATE && window.STATE.role")
        _set_role(browser, "ROLE_ORGAN_MANAGER")
        browser.eval("location.hash = ''; location.hash = '#/request-flow/review/REQ-2026-04-25-0011'")
        _wait_for(browser, "document.body.innerText.includes('共享') && (document.body.innerText.includes('无条件') || document.body.innerText.includes('有条件'))", timeout=10)
        time.sleep(1)
        screenshot(browser, OUTPUT_DIR / "02-j1-sharing-type-ui.png", viewport_height=1600)
    finally:
        browser.close()


def capture_03_provider_wizard(base_url: str) -> None:
    print("03 - J2 反向编目 wizard（P5）")
    browser = _open_browser(f"{base_url}/#/provider/wizard/reverse-catalog")
    try:
        _wait_for(browser, "document.body && document.body.innerText.length > 100", timeout=10)
        _wait_for(browser, "document.getElementById('role-switch') && window.STATE && window.STATE.role")
        _set_role(browser, "ROLE_ORGAN_MANAGER")
        browser.eval("location.hash = ''; location.hash = '#/provider/wizard/reverse-catalog'")
        _wait_for(browser, "document.body.innerText.includes('反向编目')", timeout=10)
        time.sleep(1)
        screenshot(browser, OUTPUT_DIR / "03-j2-provider-wizard.png", viewport_height=1200)
    finally:
        browser.close()


def capture_04_compliance_audit(base_url: str) -> None:
    print("04 - J3 P6 合规运营审计回放")
    browser = _open_browser(f"{base_url}/#/compliance-ops")
    try:
        _wait_for(browser, "document.body && document.body.innerText.length > 100", timeout=10)
        _wait_for(browser, "document.getElementById('role-switch') && window.STATE && window.STATE.role")
        _set_role(browser, "ROLE_SECURITY_AUDIT")
        browser.eval("location.hash = ''; location.hash = '#/compliance-ops'")
        _wait_for(browser, "document.body.innerText.length > 300", timeout=10)
        time.sleep(1)
        screenshot(browser, OUTPUT_DIR / "04-j3-compliance-audit.png", viewport_height=1400)
    finally:
        browser.close()


# capture_05_k12_dashboard_link 已删除（K12 大屏退役 R17 / v4.1）


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_service()
    server, thread, base_url = _start_rest_server()
    print(f"REST started at {base_url}")
    try:
        capture_01_j1_credential(base_url)
        capture_02_sharing_type(base_url)
        capture_03_provider_wizard(base_url)
        capture_04_compliance_audit(base_url)
        print()
        print("=" * 50)
        print(f"4 张截图已保存到 {OUTPUT_DIR.relative_to(REPO)}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    sys.exit(main())
