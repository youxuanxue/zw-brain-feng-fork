"""R-008 单一来源 mechanical alignment test.

确保所有需要"6 ROLE_* + admin/system"集合的位置都从 role_codes 派生，
或与 role_codes 保持一致（基线附录 C 禁止"多处手维护投影"）。

测试覆盖：
- policy.ACTOR_NAMES ⇔ role_codes.ROLE_DISPLAY_NAMES_ZH（dict 同步）
- server._DEV_IAM_BYPASS_ROLES ⇔ role_codes.ALL_ROLE_CODES
- alembic 0009 _ALLOWED_ROLE_CODES ⇔ role_codes.ALL_ROLE_CODES
- web_snapshot_redaction frozensets ⊆ role_codes.ALL_ROLE_CODES（只读裁剪可以是子集）
- 前端 app.js / pages.js 通过 JSON 解析对比（避免手维护漂移）
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_policy_actor_names_aligned_with_role_codes():
    from zw_brain.domain import policy, role_codes
    assert set(policy.ACTOR_NAMES.keys()) == set(role_codes.ALL_ROLE_CODES), (
        "policy.ACTOR_NAMES 必须与 role_codes.ALL_ROLE_CODES 同步；"
        "应通过 import 派生而非手维护"
    )
    assert policy.ACTOR_NAMES == role_codes.ROLE_DISPLAY_NAMES_ZH, (
        "policy.ACTOR_NAMES 内容必须等同 role_codes.ROLE_DISPLAY_NAMES_ZH"
    )


def test_server_bypass_roles_aligned_with_role_codes():
    from zw_brain.domain import role_codes
    from zw_brain.entry.rest import server
    assert set(server._DEV_IAM_BYPASS_ROLES) == set(role_codes.ALL_ROLE_CODES), (
        "server._DEV_IAM_BYPASS_ROLES 必须与 role_codes.ALL_ROLE_CODES 同步"
    )


def test_alembic_0009_allowed_codes_aligned_with_role_codes():
    from zw_brain.domain import role_codes
    mod = _load_module(REPO / "alembic" / "versions" / "0009_role_code_d23_retrofit.py", "alembic_0009_align")
    assert set(mod._ALLOWED_ROLE_CODES) == set(role_codes.ALL_ROLE_CODES), (
        "alembic 0009 _ALLOWED_ROLE_CODES 必须与 role_codes.ALL_ROLE_CODES 同步；"
        "如新增/退役角色，同改两处（或将 alembic 改为 import role_codes，"
        "但注意迁移可能在 app 不可导入时运行）"
    )


def test_web_snapshot_redaction_uses_only_known_roles():
    from zw_brain.domain import role_codes, web_snapshot_redaction
    known = set(role_codes.BUSINESS_ROLE_CODES)
    for frozenset_name in ("_DISCOVERY", "_REQUEST", "_DELIVERY", "_PROVIDER", "_COMPLIANCE", "_ZONES", "_CAPABILITY", "_OPS"):
        s = getattr(web_snapshot_redaction, frozenset_name)
        unknown = set(s) - known
        assert not unknown, (
            f"web_snapshot_redaction.{frozenset_name} 含未知角色码 {unknown}；"
            f"应只用 role_codes.BUSINESS_ROLE_CODES 中的角色"
        )


def _extract_object_keys(js_text: str, marker_pattern: str) -> set[str]:
    r"""从 JS 源代码中提取一个对象字面量的 key 名集合。

    marker_pattern 是一个能匹配 "<对象起点 { 字符" 之前那一行的正则
    （如 r'const ROLE_NAMES\s*=\s*\{' 或 r'const ROLE_HERO\s*=\s*\{'）。
    严格只在该对象的花括号范围内提取 key，避免注释/字符串假阳性。
    """
    m = re.search(marker_pattern, js_text)
    if not m:
        return set()
    start = m.end() - 1  # 落在 '{' 上
    depth = 0
    end = start
    for i in range(start, len(js_text)):
        c = js_text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = js_text[start + 1:end]
    # 抽取键：每行开头（去空白）一个标识符 + ":"，跳过注释行
    keys: set[str] = set()
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("/*") or s.startswith("*"):
            continue
        km = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", s)
        if km:
            keys.add(km.group(1))
    return keys


def test_frontend_role_names_aligned_with_backend():
    """前端 app.js ROLE_NAMES 与后端 role_codes 一致（避免后端添加角色而前端漏更）.

    F3 fix: 用对象 key 范围抽取替代 raw grep，避免注释/字符串假阳性。
    """
    from zw_brain.domain import role_codes
    app_js = (REPO / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")
    keys = _extract_object_keys(app_js, r"const ROLE_NAMES\s*=\s*\{")
    expected = set(role_codes.BUSINESS_ROLE_CODES) | {"admin"}
    missing = expected - keys
    assert not missing, f"app.js ROLE_NAMES 缺角色键 {missing}"


def test_frontend_role_hero_covers_all_business_roles():
    """前端 pages.js ROLE_HERO 必须覆盖所有 BUSINESS_ROLE_CODES.

    F3 fix: 同上，按对象 key 范围抽取。
    """
    from zw_brain.domain import role_codes
    pages_js = (REPO / "zw-brain-web" / "js" / "pages.js").read_text(encoding="utf-8")
    keys = _extract_object_keys(pages_js, r"const ROLE_HERO\s*=\s*\{")
    expected = set(role_codes.BUSINESS_ROLE_CODES)
    missing = expected - keys
    assert not missing, f"pages.js ROLE_HERO 缺角色键 {missing}"
