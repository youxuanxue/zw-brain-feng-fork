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


def test_bootstrap_exchanges_oauth_code_before_session_probe() -> None:
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    bootstrap_body = auth.split("async function _runBootstrap")[1].split("export async function bootstrap")[0]
    assert "_completeOAuthCallback" in bootstrap_body
    assert "_oauthParamsFromUrl()" in bootstrap_body
    assert bootstrap_body.index("_completeOAuthCallback") < bootstrap_body.index("_readCurrentSession")
    assert "_bootstrapInFlight" in auth


def test_auth_fetch_waits_for_bootstrap() -> None:
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    auth_fetch_body = auth.split("export async function authFetch")[1].split("export function getCurrentUser")[0]
    assert "waitForAuthBootstrap()" in auth_fetch_body


def test_app_skips_route_refresh_during_oauth_callback() -> None:
    app = (REPO / "zw-brain-web" / "src" / "App.vue").read_text(encoding="utf-8")
    assert "hasPendingOAuthCallback()" in app
    assert "role-readonly" in app
    assert "showRoleControl" in app


def test_auth_syncs_product_role_from_session() -> None:
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    assert "syncProductRoleFromSession()" in auth
    assert "current_role" in auth


def test_logout_redirects_to_iaf_logout_url() -> None:
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    logout_fn = auth.split("export async function logout")[1].split("function _openBroadcastChannel")[0]
    assert "data.logout_url" in logout_fn
    assert "window.location.href = logoutUrl" in logout_fn
    assert "window.location.href = redirectUri" not in logout_fn.split("window.location.href = logoutUrl")[0]


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


def test_app_blocks_home_when_no_product_role() -> None:
    app = (REPO / "zw-brain-web" / "src" / "App.vue").read_text(encoding="utf-8")
    auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    assert "missingProductRole" in app
    assert "hasAllowedProductRoles" in app
    assert "联系系统管理员" in app or "联系管理员" in app
    assert 'id="no-product-role-logout"' in app
    assert "@click=\"logout\"" in app
    assert "export function hasAllowedProductRoles()" in auth
    login = (REPO / "zw-brain-web" / "src" / "pages" / "PLogin.vue").read_text(encoding="utf-8")
    assert "hasAllowedProductRoles()" in login
    workbench = (REPO / "zw-brain-web" / "src" / "composables" / "useWorkbench.ts").read_text(encoding="utf-8")
    assert "hasAllowedProductRoles()" in workbench
    auth_oauth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    assert "_stripOAuthParamsFromUrl()" in auth_oauth.split("async function _completeOAuthCallback")[1].split("async function _runBootstrap")[0]
