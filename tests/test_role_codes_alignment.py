"""R-008 单一来源 mechanical alignment test.

确保所有需要"6 ROLE_* + admin/system"集合的位置都从 role_codes 派生，
或与 role_codes 保持一致（基线附录 C 禁止"多处手维护投影"）。

测试覆盖：
- policy.ACTOR_NAMES ⇔ role_codes.ROLE_DISPLAY_NAMES_ZH（dict 同步）
- server._DEV_IAM_BYPASS_ROLES_DEFAULT ⇔ role_codes.ALL_ROLE_CODES
- web_snapshot_redaction frozensets ⊆ role_codes.ALL_ROLE_CODES（只读裁剪可以是子集）
- 前端 app.js / pages.js 通过 JSON 解析对比（避免手维护漂移）

（alembic 0009 _ALLOWED_ROLE_CODES 对齐校验已在 alembic 整体删除时一并退役；详见 D23 二次升级）
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
    assert set(server._DEV_IAM_BYPASS_ROLES_DEFAULT) == set(role_codes.ALL_ROLE_CODES), (
        "server._DEV_IAM_BYPASS_ROLES_DEFAULT 必须与 role_codes.ALL_ROLE_CODES 同步"
    )


def test_dev_iam_bypass_role_codes_env_override(monkeypatch):
    """ZW_BRAIN_DEV_IAM_BYPASS_ROLES env 必须按约定覆写：

    - 未设置 → 默认全角色（向后兼容）
    - 空串 ""  → []（A3 无产品岗位重现）
    - "ROLE_X,ROLE_Y" → 精确两项
    """
    from zw_brain.domain import role_codes
    from zw_brain.entry.rest import server

    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS_ROLES", raising=False)
    assert set(server._dev_iam_bypass_role_codes()) == set(role_codes.ALL_ROLE_CODES)

    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ROLES", "")
    assert server._dev_iam_bypass_role_codes() == []

    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ROLES", "ROLE_ORGAN_OPERATER, ROLE_BUSIAUDIT")
    assert server._dev_iam_bypass_role_codes() == ["ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT"]


def test_web_snapshot_redaction_uses_only_known_roles():
    from zw_brain.domain import role_codes, web_snapshot_redaction
    known = set(role_codes.BUSINESS_ROLE_CODES)
    # provider 拆为 _PROVIDER_FULL（MANAGER+BUSIAUDIT 见所有 sub-keys）
    # 与 _PROVIDER_PARTIAL（OPERATER 仅见 catalogs），两个 frozenset 都需对齐角色码。
    for frozenset_name in (
        "_DISCOVERY", "_REQUEST", "_DELIVERY",
        "_PROVIDER_FULL", "_PROVIDER_PARTIAL",
        "_COMPLIANCE", "_ZONES", "_CAPABILITY", "_OPS",
    ):
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
    """前端 PRODUCT_ROLE_LABELS（src/composables/useAuth.ts）与后端 role_codes 一致。

    F3 fix: 旧 js/app.js ROLE_NAMES 已退役 → src/composables/useAuth.ts
    PRODUCT_ROLE_LABELS。本测试同步迁。`admin` 是 dev/调试用户的合成角色码，
    不属于业务角色矩阵，因此 PRODUCT_ROLE_LABELS 不要求包含。
    """
    from zw_brain.domain import role_codes
    use_auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    keys = _extract_object_keys(use_auth, r"PRODUCT_ROLE_LABELS\s*:\s*Record<string, string>\s*=\s*\{")
    expected = set(role_codes.BUSINESS_ROLE_CODES)
    missing = expected - keys
    assert not missing, f"useAuth.ts PRODUCT_ROLE_LABELS 缺角色键 {missing}"


def test_frontend_role_hero_covers_all_business_roles():
    """所有 BUSINESS_ROLE_CODES 必须在 vite source 树中可被引用（router meta + 角色门禁）。

    F3 fix: 旧 pages.js ROLE_HERO 退役 → 检查 src/ 中至少有 PRODUCT_ROLE_CODES 数组
    + PRODUCT_ROLE_LABELS 同时声明，且两者覆盖所有业务角色。
    """
    from zw_brain.domain import role_codes
    use_auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    codes = _extract_array_string_literals(use_auth, r"PRODUCT_ROLE_CODES\s*=\s*\[")
    expected = set(role_codes.BUSINESS_ROLE_CODES)
    missing = expected - codes
    assert not missing, f"useAuth.ts PRODUCT_ROLE_CODES 缺角色键 {missing}"


def _extract_array_string_literals(js_text: str, marker_pattern: str) -> set[str]:
    r"""从 JS 源代码中提取一个字符串数组字面量的元素集合。

    marker_pattern 匹配 "<标识符 = [" 之前那一行的正则
    （如 r'const PRODUCT_ROLE_CODES\s*=\s*\['）。
    严格只在该数组的方括号范围内提取 'xx' / "xx" 字面量。
    """
    m = re.search(marker_pattern, js_text)
    if not m:
        return set()
    start = m.end() - 1  # 落在 '[' 上
    depth = 0
    end = start
    for i in range(start, len(js_text)):
        c = js_text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = js_text[start + 1:end]
    return set(re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", body))


def test_frontend_auth_product_role_codes_aligned_with_backend():
    """useAuth.ts PRODUCT_ROLE_CODES 驱动岗位切换前端门禁，必须与 BUSINESS_ROLE_CODES 完全一致。

    一旦后端 BUSINESS_ROLE_CODES 增删，本测试会先于 UX bug 拦下漂移。
    F3 迁移：旧 js/auth.js → src/composables/useAuth.ts 同名常量。
    """
    from zw_brain.domain import role_codes
    use_auth = (REPO / "zw-brain-web" / "src" / "composables" / "useAuth.ts").read_text(encoding="utf-8")
    codes = _extract_array_string_literals(use_auth, r"PRODUCT_ROLE_CODES\s*=\s*\[")
    assert codes == set(role_codes.BUSINESS_ROLE_CODES), (
        f"useAuth.ts PRODUCT_ROLE_CODES 与 role_codes.BUSINESS_ROLE_CODES 漂移；"
        f"useAuth.ts={sorted(codes)} expected={sorted(role_codes.BUSINESS_ROLE_CODES)}"
    )
