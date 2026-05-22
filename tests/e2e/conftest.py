"""Wave 0+ Playwright e2e shared config.

Single source of base URL / headless / slow-mo / screenshot dir so Wave 1
golden-path scripts reuse the same launch knobs. Importable as a plain module
(`from tests.e2e.conftest import E2EConfig`) and usable as a pytest conftest.

The local shell may export HTTP(S)_PROXY pointing at a personal proxy
(e.g. 127.0.0.1:7890) which 502s on the loopback service. Chromium must launch
with --no-proxy-server so 127.0.0.1:8800 is hit directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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
