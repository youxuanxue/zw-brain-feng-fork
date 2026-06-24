"""REST 边界：客户端提前断开（BrokenPipe/ConnectionReset）静默收口、不外抛 traceback。

回归锚：RestHandler.handle_one_request 在请求边界**一处**捕获写时断开异常，覆盖所有写路径
（_json/_serve_file/_redirect/_empty/_respond_*）——而非逐方法 try。守两件事：
①断开异常被吞且标记关连接（不污染日志）；②非断开异常照常上抛（不过度吞错）。
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

import pytest

from zw_brain.entry.rest.server import RestHandler

pytestmark = pytest.mark.no_db


def _bare_handler() -> RestHandler:
    # 绕开 socket __init__：只测 handle_one_request 的边界捕获逻辑。
    handler = RestHandler.__new__(RestHandler)
    handler.close_connection = False
    return handler


@pytest.mark.parametrize("exc", [BrokenPipeError, ConnectionResetError])
def test_handle_one_request_swallows_client_disconnect(exc: type[BaseException]) -> None:
    handler = _bare_handler()
    with patch.object(BaseHTTPRequestHandler, "handle_one_request", side_effect=exc()):
        handler.handle_one_request()  # 不得外抛
    assert handler.close_connection is True, "断开后应标记关连接，不留半开连接"


def test_handle_one_request_propagates_non_disconnect_errors() -> None:
    # 不过度吞错：真正的程序错误必须照常上抛（否则会把 bug 静默掉）。
    handler = _bare_handler()
    with patch.object(BaseHTTPRequestHandler, "handle_one_request", side_effect=ValueError("boom")):  # noqa: SIM117
        with pytest.raises(ValueError, match="boom"):
            handler.handle_one_request()
