#!/usr/bin/env python3
"""Mechanical gate: shipped WebUI stays on UI Spec B.

Canonical reference: spec/ui/gov-ui-spec-b-service.html.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "spec" / "ui" / "gov-ui-spec-b-service.html"

CANONICAL_WEB_TOKENS = {
    "--b-primary": "#006be6",
    "--b-primary-hover": "#0056c7",
    "--b-primary-active": "#0048a8",
    "--b-secondary": "#009688",
    "--b-bg-page": "#f2f7fd",
    "--b-bg-card": "#ffffff",
    "--b-bg-subtle": "#e8f2fc",
    "--b-border": "#d4e2f4",
    "--b-neutral-text": "#1a1d21",
    "--b-muted": "#5c6370",
}

# K12 dashboard retired in v4.1 二轮再砍 (R17); CANONICAL_DASH_TOKENS removed.

CANONICAL_VISUAL_ROUTES = {
    "#/p1-workbench",
    "#/p2-discovery",
    "#/p3-request-flow",
    "#/p4-delivery-exchange",
    "#/p5-provider",
    "#/p6-compliance-ops",
    "#/p7-zones-pack",
    "#/p8-integration-admin",
}

FORBIDDEN_WEB_PATTERNS = [
    (re.compile(r"cdn\.tailwindcss\.com", re.I), "Tailwind CDN"),
    (re.compile(r"tailwind\.config", re.I), "tailwind.config inline theme"),
    (re.compile(r"#12386f", re.I), "legacy zw-primary navy (#12386f)"),
    (re.compile(r"#1d5a9f", re.I), "legacy accent navy (#1d5a9f)"),
    (re.compile(r"Spec B|一网通办|Command View", re.I), "style-spec or cockpit copy leaked into shipped WebUI"),
    (re.compile(r"\bD\d+\b", re.I), "internal decision id leaked into shipped WebUI"),
    (re.compile(r"Actor 投影", re.I), "internal actor projection term leaked into shipped WebUI"),
    (re.compile(r"Capability Policy", re.I), "internal capability policy term leaked into shipped WebUI"),
    (re.compile(r"fail-closed", re.I), "internal fail-closed term leaked into shipped WebUI"),
    (re.compile(r"OIDC|OpenID Connect", re.I), "protocol-level auth term leaked into shipped WebUI"),
    (re.compile(r"ZW_BRAIN_", re.I), "environment variable name leaked into shipped WebUI"),
    (re.compile(r"演示环境|占位", re.I), "demo or placeholder wording leaked into shipped WebUI"),
    (re.compile(r"--dash-|dash-stage|dash-command-grid|dark data|cockpit", re.I), "dark dashboard remnants in shipped WebUI"),
    (re.compile(r"#050d18|#061428|#071528|#0a1628|#e8f1ff", re.I), "dark cockpit palette in shipped WebUI"),
]

SHIPPED_WEB_ROOTS = [
    REPO / "zw-brain-web",
]

SHIPPED_WEB_ASSETS = [
    path
    for root in SHIPPED_WEB_ROOTS
    if root.is_dir()
    for path in sorted(root.rglob("*"))
    if path.suffix in {".html", ".css", ".js"}
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require_file(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"missing {path.relative_to(REPO)}")
        return ""
    return read(path)


def require_tokens(path: Path, text: str, tokens: dict[str, str], errors: list[str]) -> None:
    lowered = text.lower()
    for token, value in tokens.items():
        needle = f"{token}: {value}"
        if needle not in text and needle.lower() not in lowered:
            errors.append(f"{path.relative_to(REPO)} must define exact token {needle}")


def require_spec_contract(spec: str, errors: list[str]) -> None:
    required = {
        'data-spec-contract="typography"': "canonical spec must define typography contract",
        'data-spec-contract="spacing"': "canonical spec must define spacing contract",
        'data-spec-contract="components"': "canonical spec must define component contract",
        'data-spec-contract="forbidden"': "canonical spec must define forbidden patterns",
        '<code>text-display</code>': "canonical spec must define text-display",
        '<code>page-hero-title</code>': "canonical spec must define page hero title typography",
        '<code>panel-title</code>': "canonical spec must define panel title typography",
        '<code>text-body</code>': "canonical spec must define body typography",
        '<code>text-body-sm</code>': "canonical spec must define body-small typography",
        '<code>text-caption</code>': "canonical spec must define caption typography",
        '30px / 700 / 1.2': "canonical spec must define display scale",
        '24px / 700 / 1.3': "canonical spec must define hero title scale",
        '18px / 700 / 1.4': "canonical spec must define panel title scale",
        '15px / 400 / 1.65': "canonical spec must define body scale",
        '14px / 400 / 1.65': "canonical spec must define body-small scale",
        '13px / 400 / 1.5': "canonical spec must define caption scale",
        '8px 11px': "canonical spec must define compact page-hero padding",
        '<code>crumbs</code>': "canonical spec must define breadcrumb component",
        '<code>page-hero</code>': "canonical spec must define page hero component",
        '<code>panel</code>': "canonical spec must define panel component",
        '<code>gov-stat-card</code>': "canonical spec must define stat card component",
        '<code>gov-btn</code>': "canonical spec must define button component",
        '<code>product-nav-link</code>': "canonical spec must define product nav component",
    }
    for needle, message in required.items():
        if needle not in spec:
            errors.append(f"{SPEC.relative_to(REPO)}: {message}")

    for token, value in CANONICAL_WEB_TOKENS.items():
        needle = f"{token}: {value}"
        if needle not in spec and needle.upper() not in spec.upper():
            errors.append(f"{SPEC.relative_to(REPO)} must define canonical token {needle}")


def scan_forbidden(path: Path, text: str, errors: list[str]) -> None:
    for rx, label in FORBIDDEN_WEB_PATTERNS:
        if rx.search(text):
            errors.append(f"forbidden in {path.relative_to(REPO)}: {label}")


def js_route_regexes(app_js: str) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for source in re.findall(r"test:\s*/\^(#.*?)\$/", app_js):
        py_source = source.replace(r"\/", "/")
        patterns.append(re.compile(f"^{py_source}$"))
    return patterns


def literal_hash_routes(text: str) -> set[str]:
    routes: set[str] = set()
    for _quote, route in re.findall(r"(['\"])(#/[A-Za-z0-9_./:-]+)\1", text):
        if "${" not in route:
            routes.add(route)
    return routes


def route_is_reachable(route: str, route_patterns: list[re.Pattern[str]]) -> bool:
    if any(pattern.match(route) for pattern in route_patterns):
        return True
    if route.endswith("/"):
        return any(pattern.match(f"{route}__id__") for pattern in route_patterns)
    return False


def require_literal_routes_reachable(app_js: str, errors: list[str]) -> None:
    route_patterns = js_route_regexes(app_js)
    if not route_patterns:
        errors.append("zw-brain-web/js/app.js must declare route patterns")
        return

    for asset in SHIPPED_WEB_ASSETS:
        if "zw-brain-web" not in asset.parts:
            continue
        for route in sorted(literal_hash_routes(read(asset))):
            if route == "#/":
                continue
            if not route_is_reachable(route, route_patterns):
                errors.append(f"hard-coded route {route} in {asset.relative_to(REPO)} is not matched by app.js ROUTES")


def require_visual_routes_guarded(app_js: str, errors: list[str]) -> None:
    for route in sorted(CANONICAL_VISUAL_ROUTES):
        if not route_is_reachable(route, js_route_regexes(app_js)):
            errors.append(f"canonical visual route {route} is not matched by app.js ROUTES")
    restricted_refreshes = {
        "#/p4-delivery-exchange": "delivery.list",
        "#/p5-provider": "provider.view",
        "#/p6-compliance-ops": "governance.dispute_list",
        "#/p8-integration-admin": "package.list",
    }
    for route, skill_id in restricted_refreshes.items():
        marker = f"route === '{route}' && roleCan"
        if marker not in app_js:
            errors.append(f"restricted visual route {route} must guard {skill_id} refresh by roleCan")


def require_web_layout(sheet: str, errors: list[str]) -> None:
    required = {
        "font-family: \"Microsoft YaHei\", \"PingFang SC\", \"Noto Sans SC\", system-ui, sans-serif": "global font stack must follow Spec B government-service typography",
        "--zw-shell-content-max: 1500px": "main WebUI shell width must align with Spec B layout width",
        "--zw-main-pad-y: 24px": "main shell vertical rhythm must remain stable",
        "grid-template-columns: var(--zw-product-nav-w) minmax(0, 1fr)": "business nav must use normal two-column layout",
        "position: static": "business nav must stay in document flow and align with the first content card",
        ".page-hero {\n  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);\n  border: 1px solid var(--b-border);\n  border-radius: var(--b-radius-md);\n  padding: 8px 11px;": "page hero must use compact Spec B service-card spacing",
        ".page-hero-title {\n  font-size: 24px;": "page hero title must use normalized Spec B title size",
        ".page-hero-subtitle {\n  margin-top: 8px;\n  font-size: 14px;": "page hero subtitle must keep hint-level hierarchy below primary body size",
        ".panel-title {\n  font-size: 18px;": "panel titles must use normalized Spec B component typography",
        ".panel-subtitle {\n  margin-top: 8px;\n  font-size: 14px;": "panel subtitles must stay visually secondary to primary panel content",
        ".gov-stat-note": "stat card notes must use normalized typography class",
        ".gov-stat-action": "stat card actions must use normalized typography class",
        "a {\n  color: inherit;\n  text-decoration: none;": "global links must not fall back to browser default underline/purple styling",
    }
    for needle, message in required.items():
        if needle not in sheet:
            errors.append(f"zw-brain-web/css/app.css: {message}")

    floating_nav = re.search(
        r"\.product-shell-grid:not\(\.is-shell-nav-collapsed\) \.product-shell-aside\s*\{[^}]*position:\s*(fixed|sticky)",
        sheet,
        re.S,
    )
    if floating_nav:
        errors.append("business nav must stay in normal document flow so its top aligns with the first content card")

    forbidden_css = {
        ".text-xs": "WebUI CSS must not retain raw text-xs compatibility utilities",
        ".text-sm": "WebUI CSS must not retain raw text-sm compatibility utilities",
    }
    for needle, message in forbidden_css.items():
        if needle in sheet:
            errors.append(f"zw-brain-web/css/app.css: {message}")


# K12 dashboard typography check retired in v4.1 二轮再砍 (R17).


def require_web_typography(path: Path, text: str, errors: list[str]) -> None:
    required = {
        'class="text-body leading-7 text-zw-ink flex-1"': "inline summaries must use Spec B body typography",
        'class="text-body mt-3 leading-7">${zone.desc}</p>': "zone card descriptions must use Spec B body typography",
        'class="mt-4 row-meta">资产 ${zone.assets.length} 项 · 订阅部门 ${zone.subscribers}</div>': "zone card metadata must use normalized row-meta typography",
        'class="space-y-2 text-body leading-7 list-disc pl-5"': "zone detail lists must use Spec B body typography",
        'class="text-body-sm text-zw-mute mb-2 flex items-center gap-2 flex-wrap crumbs"': "breadcrumbs must use readable Spec B body-small typography above page hero",
        'items-center gap-2 text-caption text-zw-mute': "step bars must use caption typography without extra card-bottom spacing",
        '<div class="mt-4">${stepBar': "step bars must follow compact Spec B hero spacing",
    }
    for needle, message in required.items():
        if needle not in text:
            errors.append(f"{path.relative_to(REPO)}: {message}")

    forbidden = {
        'class="text-sm leading-7 text-zw-ink flex-1"': "inline summaries must not use raw text-sm",
        'class="text-sm mt-3 leading-7">${zone.desc}</p>': "zone card descriptions must not use raw text-sm",
        'class="mt-4 text-xs text-zw-mute">资产 ${zone.assets.length} 项 · 订阅部门 ${zone.subscribers}</div>': "zone card metadata must not use raw text-xs",
        'class="space-y-2 text-sm list-disc pl-5"': "zone detail lists must not use raw text-sm",
        'class="text-caption text-zw-mute mb-4 flex items-center gap-2 flex-wrap crumbs"': "breadcrumbs must not create oversized gap above page hero",
        'class="text-caption text-zw-mute mb-2 flex items-center gap-2 flex-wrap crumbs"': "breadcrumbs must not use tiny caption typography",
        'mb-5 text-xs text-zw-mute': "step bars must not use raw text-xs",
        'mb-5 text-caption text-zw-mute': "step bars must not add extra bottom spacing inside hero cards",
        '<div class="mt-5">${stepBar': "page hero step bars must not use oversized top spacing",
    }
    for needle, message in forbidden.items():
        if needle in text:
            errors.append(f"{path.relative_to(REPO)}: {message}")

    raw_text_classes = re.findall(r"class=\"[^\"]*(?:text-sm|text-xs)[^\"]*\"", text)
    if raw_text_classes:
        errors.append(f"{path.relative_to(REPO)} must use Spec B semantic typography classes, found raw size classes: {', '.join(sorted(set(raw_text_classes)))}")



def require_catalog_metadata_capability_actions(app_js: str, errors: list[str]) -> None:
    required = {
        "performWrite('application.resource.submit'": "resource application must use canonical application.resource.submit Capability",
        "performWrite('application.resource.review'": "resource approval must use canonical application.resource.review Capability",
        "performWrite('backflow.confirm'": "backflow confirmation must use canonical backflow.confirm Capability",
        "performWrite('catalog.entry.publish'": "catalog publish must use canonical catalog.entry.publish Capability",
        "performWrite('resource.asset.publish'": "resource publish must use canonical resource.asset.publish Capability",
    }
    for needle, message in required.items():
        if needle not in app_js:
            errors.append(f"zw-brain-web/js/app.js: {message}")

    forbidden = {
        "performWrite('request.create'": "resource application must not use legacy request.create from the catalog/metadata journey",
        "performWrite('approval.review_decide'": "resource approval must not use legacy approval.review_decide from the catalog/metadata journey",
    }
    for needle, message in forbidden.items():
        if needle in app_js:
            errors.append(f"zw-brain-web/js/app.js: {message}")


def main() -> int:
    errors: list[str] = []

    web_index = REPO / "zw-brain-web" / "index.html"
    web_css = REPO / "zw-brain-web" / "css" / "app.css"

    spec = require_file(SPEC, errors)
    html = require_file(web_index, errors)
    sheet = require_file(web_css, errors)

    app_js = REPO / "zw-brain-web" / "js" / "app.js"
    pages_js = REPO / "zw-brain-web" / "js" / "pages.js"
    app_script = require_file(app_js, errors)
    pages_script = require_file(pages_js, errors)

    if spec:
        require_spec_contract(spec, errors)

    if html:
        if 'href="/css/app.css"' not in html and "href='/css/app.css'" not in html:
            errors.append("zw-brain-web/index.html must link /css/app.css")
        if "ui-spec-b" not in html:
            errors.append("zw-brain-web/index.html body must declare ui-spec-b")

    if sheet:
        require_tokens(web_css, sheet, CANONICAL_WEB_TOKENS, errors)
        require_web_layout(sheet, errors)

    if app_script:
        require_literal_routes_reachable(app_script, errors)
        require_visual_routes_guarded(app_script, errors)
        require_catalog_metadata_capability_actions(app_script, errors)

    if pages_script:
        require_web_typography(pages_js, pages_script, errors)

    for asset in SHIPPED_WEB_ASSETS:
        scan_forbidden(asset, read(asset), errors)

    if errors:
        print("check_ui_spec_b: FAIL", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("check_ui_spec_b: OK (Spec B tokens + no Tailwind / legacy navy in shipped WebUI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
