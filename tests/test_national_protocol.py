"""C3 — 数据直达协议层单测（签名/envelope/返回码/client），无网络、无 seed。

签名用**固定向量**钉死算法（接口规范 v0.55 附录C：base64(HmacSHA256(sid+rid+rtime, appsecret))）。
client 经协议合规桩 round-trip，证明我方会"说协议"。
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from tests.national_stub import ProtocolViolation, make_stub_transport
from zw_brain.shared.national.client import NationalDirectClient
from zw_brain.shared.national.envelope import (
    HEADER_RID,
    HEADER_SID,
    HEADER_SIGN,
    MissingInterfaceSidError,
    build_body,
    build_headers,
)
from zw_brain.shared.national.provisioning import NationalProvisioning
from zw_brain.shared.national.return_codes import NationalResponse, parse_response
from zw_brain.shared.national.signing import sign_request


def _prov() -> NationalProvisioning:
    return NationalProvisioning(
        endpoint="http://10.0.0.1:8080",
        rid="rid-sd",
        appkey="appkey-x",
        appsecret="secret-x",
        sid_map={"catalog.report": "sid-cat-001", "application.submit": "sid-app-001"},
    )


def test_sign_request_fixed_vector() -> None:
    # 独立复算（不复用被测实现的拼接），钉死 sid+rid+rtime 顺序与 HMAC-SHA256/base64。
    sid, rid, rtime, secret = "sid-cat-001", "rid-sd", "1700000000000", "secret-x"
    expect = base64.b64encode(
        hmac.new(secret.encode(), f"{sid}{rid}{rtime}".encode(), hashlib.sha256).digest()
    ).decode("ascii")
    assert sign_request(sid=sid, rid=rid, rtime=rtime, appsecret=secret) == expect
    # 顺序敏感：rid+sid+rtime 应得到不同签名（守住拼接顺序不被无意改动）。
    wrong = base64.b64encode(
        hmac.new(secret.encode(), f"{rid}{sid}{rtime}".encode(), hashlib.sha256).digest()
    ).decode("ascii")
    assert sign_request(sid=sid, rid=rid, rtime=rtime, appsecret=secret) != wrong


def test_build_headers_signs_and_requires_sid() -> None:
    headers = build_headers(_prov(), "catalog.report", "1700000000000")
    assert headers[HEADER_RID] == "rid-sd"
    assert headers[HEADER_SID] == "sid-cat-001"
    assert headers[HEADER_SIGN] == sign_request(
        sid="sid-cat-001", rid="rid-sd", rtime="1700000000000", appsecret="secret-x"
    )
    with pytest.raises(MissingInterfaceSidError):
        build_headers(_prov(), "unknown.interface", "1700000000000")


def test_build_body_lowercases_keys_recursively() -> None:
    body = build_body({"CataTitle": "X", "Columns": [{"NameCn": "信息项"}], "nested": {"Foo": 1}})
    assert body == {"catatitle": "X", "columns": [{"namecn": "信息项"}], "nested": {"foo": 1}}


def test_parse_response_success_and_failure() -> None:
    ok = parse_response({"code": "200", "message": "成功", "data": {"cataId": "X"}})
    assert ok.ok and ok.data == {"cataId": "X"} and ok.error_domain is None
    fail = parse_response({"code": "300", "message": "catalog-002 重复的目录编码！"})
    assert not fail.ok and fail.error_domain == "catalog"
    # fail-closed：缺 code → 失败
    assert parse_response({}).ok is False
    assert parse_response("nope").ok is False  # type: ignore[arg-type]


def test_client_roundtrip_through_protocol_stub() -> None:
    captured: list[dict] = []
    transport = make_stub_transport(
        appsecret="secret-x",
        canned={"code": "200", "message": "成功", "data": {"cataId": "NAT-001"}},
        captured=captured,
    )
    client = NationalDirectClient(
        provisioning=_prov(),
        transport=transport,
        clock=lambda: 1700000000000,
    )
    resp = client.post(
        interface_name="catalog.report",
        path="catalog/report",
        payload={"CataTitle": "测试上报目录", "OrganCode": "TE370000"},
    )
    assert isinstance(resp, NationalResponse)
    assert resp.ok and resp.data == {"cataId": "NAT-001"}
    # 桩捕获到的请求：URL 走 /sysapi/，body 已小写化。
    assert captured[0]["url"] == "http://10.0.0.1:8080/sysapi/catalog/report"
    assert captured[0]["body"] == {"catatitle": "测试上报目录", "organcode": "TE370000"}


def test_stub_rejects_tampered_signature() -> None:
    # 桩用不同 appsecret 复算 → client 的签名必然对不上 → ProtocolViolation。
    transport = make_stub_transport(appsecret="WRONG-secret")
    client = NationalDirectClient(provisioning=_prov(), transport=transport, clock=lambda: 1)
    with pytest.raises(ProtocolViolation):
        client.post(interface_name="catalog.report", path="catalog/report", payload={"a": 1})


def test_client_handles_nonjson_response() -> None:
    def bad_transport(url, headers, body):
        return 502, b"<html>gateway error</html>"

    client = NationalDirectClient(provisioning=_prov(), transport=bad_transport, clock=lambda: 1)
    resp = client.post(interface_name="catalog.report", path="catalog/report", payload={})
    assert not resp.ok and "解析失败" in resp.message
