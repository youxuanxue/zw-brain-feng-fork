"""读路径资源类型折叠守卫（D53：只支持 库表/文件/API）。

存量库残留 legacy resource_kind='folder'/'url'/'link' 的行（归一化上线前导入），任何读路径
投影到消费面都必须经 canonical_resource_kind 折叠，否则 folder/url 泄漏到「资源类型」筛选/徽标
（违 D53 + R12 裸英文）。本测试钉死折叠表，防回潮。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.resource_kind import canonical_resource_kind

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 收敛三态原样
        ("table", "table"),
        ("file", "file"),
        ("api", "api"),
        # legacy 同义词折叠
        ("folder", "file"),
        ("url", "file"),
        ("link", "file"),
        ("service", "api"),
        # 大小写 / 空白容错
        ("FOLDER", "file"),
        ("  Url ", "file"),
        ("Service", "api"),
        # 空 / 未知 → None（读路径诚实空态，不臆造 table、不裸出英文）
        (None, None),
        ("", None),
        ("   ", None),
        ("mystery_kind", None),
        ("catalog_entry", None),
    ],
)
def test_canonical_resource_kind(raw: object, expected: str | None) -> None:
    assert canonical_resource_kind(raw) == expected


@pytest.mark.parametrize(
    ("res_type", "channel", "expected"),
    [
        # res_type 优先（存量极少有）
        ("api", "table", "api"),
        ("folder", None, "file"),
        # F3：res_type 缺供（62/64 行）→ 用交付渠道兜底推导，否则按钮永不分流
        (None, "service", "api"),
        (None, "table", "table"),
        (None, "file", "file"),
        (None, "folder", "file"),
        (None, "db", "table"),
        (None, "exchange", "table"),
        (None, "recurring_exchange", "table"),
        # 推不出（复合中文模式渠道）→ None（前端默认双按钮，安全）
        (None, "受控交付 + 审计回执", None),
        (None, None, None),
    ],
)
def test_delivery_resource_kind_channel_fallback(
    res_type: object, channel: object, expected: str | None
) -> None:
    from zw_brain.domain.services.delivery_service import _delivery_resource_kind

    assert _delivery_resource_kind(res_type, channel) == expected


def test_credential_resolve_resource_kind_folds_via_canonical() -> None:
    """F5：credential「查看授权」反查的资源类型必须经 canonical 折叠——legacy ``service`` 形态
    接口资源 → ``api``（否则前端显通用「凭据」而非「网关授权码」，违 D53 单一事实源）。"""
    from types import SimpleNamespace

    from zw_brain.command.handlers.j1.credential import _resolve_resource_kind

    def _deps(kind: object) -> object:
        repo = SimpleNamespace(get_asset=lambda _rid: SimpleNamespace(resource_kind=kind))
        return SimpleNamespace(repos=SimpleNamespace(resource_api=repo))

    assert _resolve_resource_kind(_deps("service"), "res-x") == "api"
    assert _resolve_resource_kind(_deps("folder"), "res-x") == "file"
    assert _resolve_resource_kind(_deps("table"), "res-x") == "table"
    assert _resolve_resource_kind(_deps("mystery"), "res-x") is None
    # 资源 id 缺失 → None（诚实未知，前端按通用「凭据」兜底）。
    assert _resolve_resource_kind(_deps("api"), None) is None


def test_credential_kind_prefers_delivery_then_asset() -> None:
    """F5-W2：凭据页类型优先用交付任务 resourceKind(与列表 F3 同源，保证两页口径一致)，
    缺则反查资源主表；两路都无 → None（诚实兜底，不臆断 API）。"""
    from types import SimpleNamespace

    from zw_brain.command.handlers.j1.credential import _credential_resource_kind

    def _deps(asset_kind: object) -> object:
        repo = SimpleNamespace(get_asset=lambda _rid: SimpleNamespace(resource_kind=asset_kind))
        return SimpleNamespace(repos=SimpleNamespace(resource_api=repo))

    # 交付任务自带 resourceKind → 直接采用（canonical 幂等折叠 service→api），不依赖主表反查
    assert _credential_resource_kind(_deps(None), {"resourceKind": "api", "resourceId": "x"}) == "api"
    assert _credential_resource_kind(_deps(None), {"resourceKind": "service", "resourceId": "x"}) == "api"
    # 交付任务无 kind → 回退反查资源主表
    assert _credential_resource_kind(_deps("service"), {"resourceId": "x"}) == "api"
    # 两路都查不到 → None
    assert _credential_resource_kind(_deps(None), {"resourceId": None}) is None


def test_credential_unissued_hint_by_kind() -> None:
    """F5-W1：未签发文案随类型——API「授权尚未签发」、库表/文件/未知「凭据尚未签发」
    （与页头名词同源，避免「凭据」页配「授权尚未签发」自相矛盾）。"""
    from zw_brain.command.handlers.j1.credential import _credential_unissued_hint

    assert _credential_unissued_hint("api").startswith("授权尚未签发")
    assert _credential_unissued_hint("table").startswith("凭据尚未签发")
    assert _credential_unissued_hint("file").startswith("凭据尚未签发")
    assert _credential_unissued_hint(None).startswith("凭据尚未签发")
