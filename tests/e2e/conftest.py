"""Wave 0+ Playwright e2e shared config.

Single source of base URL / headless / slow-mo / screenshot dir so Wave 1
golden-path scripts reuse the same launch knobs. Importable as a plain module
(`from tests.e2e.conftest import E2EConfig`) and usable as a pytest conftest.

The local shell may export HTTP(S)_PROXY pointing at a personal proxy
(e.g. 127.0.0.1:7890) which 502s on the loopback service. Chromium must launch
with --no-proxy-server so 127.0.0.1:8800 is hit directly.

Also exposes a shared `api_post(page, skill, payload)` helper that drives a
skill via `window.ZW_AUTH.authFetch` —— CSRF token auto-injected, so call
sites stop reinventing HTTP clients (urlopen + Cookie header is brittle and
can mask backend rejection paths as CSRF rejections; see R-G1-001).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = REPO_ROOT / ".data" / "customer-acceptance" / "wave0" / "screenshots"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class E2EConfig:
    base_url: str = os.environ.get("ZW_E2E_BASE_URL", "http://127.0.0.1:8800")
    # headless True = regression run; set ZW_E2E_HEADLESS=0 for a headed demo capture.
    headless: bool = field(default_factory=lambda: _env_bool("ZW_E2E_HEADLESS", True))
    slow_mo_ms: int = int(os.environ.get("ZW_E2E_SLOWMO", "0"))
    screenshot_dir: Path = SCREENSHOT_DIR
    # Loopback proxy bypass — see module docstring.
    launch_args: tuple = ("--no-proxy-server",)
    nav_timeout_ms: int = int(os.environ.get("ZW_E2E_NAV_TIMEOUT", "20000"))

    def ensure_dirs(self) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)


CONFIG = E2EConfig()


def api_post(page: Any, skill: str, payload: dict) -> dict:
    """Drive a write skill via `window.ZW_AUTH.authFetch` (CSRF auto-injected).

    Returns a dict::

        {"status": int, "ok": bool, "body": str, "result": dict | None,
         "error": str | None}

    `status >= 400` and `ok = False` indicate rejection; callers can inspect
    `body` for the exact error code (e.g. `"purpose"` literal). Direct
    `context.request.post` / `urlopen` bypass CSRF and rejection paths get
    masked as 403 csrf_token_invalid —— see R-G1-001 / G2.3 in PR-G2.
    """
    payload_json = json.dumps(payload, ensure_ascii=False)
    js = f"""
    async () => {{
      const resp = await window.ZW_AUTH.authFetch('/api/skills/{skill}', {{
        method: 'POST',
        headers: {{ 'Accept': 'application/json', 'Content-Type': 'application/json' }},
        body: {json.dumps(payload_json)},
      }});
      const text = await resp.text();
      return {{ status: resp.status, body: text }};
    }}
    """
    out = page.evaluate(js)
    status = int(out.get("status") or 0)
    body = str(out.get("body") or "")
    parsed: dict | None = None
    try:
        parsed = json.loads(body) if body else None
    except (ValueError, TypeError):
        parsed = None
    ok = bool(parsed and parsed.get("ok"))
    return {
        "status": status,
        "ok": ok,
        "body": body,
        "result": (parsed or {}).get("result") if parsed else None,
        "error": (parsed or {}).get("error") if parsed else None,
    }
