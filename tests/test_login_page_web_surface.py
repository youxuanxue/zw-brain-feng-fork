"""登录页 Web 消费面：/#/login 必须是可操作的登录面板，而非占位页。"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_login_route_uses_plogin_page() -> None:
    router = (REPO / "zw-brain-web" / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    page = (REPO / "zw-brain-web" / "src" / "pages" / "PLogin.vue").read_text(encoding="utf-8")
    assert "import PLogin from '@/pages/PLogin.vue'" in router
    assert "/login', component: PLogin" in router
    assert "login-gate-card" in page
    assert 'id="login-gate-iam"' in page
    assert 'id="login-gate-submit"' in page
    assert "loginWithIam" in page
    assert "loginWithDevBypass" in page


def test_login_does_not_auto_pick_dev_bypass() -> None:
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    login_fn = auth.split("export async function login(): Promise")[1].split("export async function logout")[0]
    assert "_devBypassLogin()" not in login_fn
    assert "loginWithIam()" in login_fn


def test_bootstrap_does_not_auto_dev_bypass() -> None:
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    assert "_devBypassLogin()" not in auth.split("export async function bootstrap")[1].split("export async function authFetch")[0]


def test_role_switch_uses_soft_snapshot_load() -> None:
    app = (REPO / "zw-brain-web" / "src" / "App.vue").read_text(encoding="utf-8")
    snap = (REPO / "zw-brain-web" / "src" / "composables" / "useSnapshot.ts").read_text(encoding="utf-8")
    assert "soft: true" in app
    assert "soft?: boolean" in snap
    assert "_cache" in snap


def test_allowed_roles_reactive_after_login() -> None:
    app = (REPO / "zw-brain-web" / "src" / "App.vue").read_text(encoding="utf-8")
    assert "const allowedRoles = computed" in app
    assert "getAllowedProductRoles()" in app
    assert "allowedRoles.value =" not in app
