"""HTTP 响应安全收口：Server banner 去版本化 + 安全响应头（单一事实源）。

漏扫 0609 整改 Layer 1：REST(:8800) 与 A2A(:8801) 都基于 stdlib ``BaseHTTPRequestHandler``，
默认会回 ``Server: BaseHTTP/0.x Python/3.12.13`` 泄漏 Python 版本——扫描器据该版本字符串匹配出
"Python DoS / HTTP Server Banner / type" 三类发现。两个入口共用本模块：

- ``SERVER_BANNER``：不含版本号的固定 banner。
- ``security_headers(is_https=...)``：一处定义全部安全响应头，两个 handler 在唯一的
  ``end_headers()`` chokepoint 注入，覆盖所有写路径（JSON / 静态文件 / 重定向 / 错误页）。

不在此"修复" CPython DoS 本身——遮蔽 banner 只降信息泄漏面并消除版本匹配发现；CPython 真正补丁
来自周期性重建镜像拉取最新 ``python:3.12-slim``。详见 docs/deployment/security-hardening-0609.md。
"""
from __future__ import annotations

# 去掉 stdlib 默认的 "BaseHTTP/x.y Python/a.b.c"，只暴露产品名、不暴露运行时版本。
SERVER_BANNER = "zw-brain"

# Content-Security-Policy:
# 构建产物 zw-brain-web/dist-vite/index.html 只引用同源外部 module 脚本、零内联脚本，
# 故 script-src 'self' 诚实可行（不掺 'unsafe-inline' 的安全剧场）；style-src 含 'unsafe-inline'
# 仅因 Vue 运行时 :style 绑定需要；connect-src 'self' 覆盖同源 /api /auth；IAM 登录是顶层导航
# （form-action/navigation，不受 connect-src 限制）。
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

# 与请求 scheme 无关、始终注入的安全头。
_STATIC_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", _CONTENT_SECURITY_POLICY),
    ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
)

# HSTS 仅在 HTTPS 下发——明文 HTTP（本地/测试）发 HSTS 会把后续访问强制升级到不存在的 TLS。
_HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


def security_headers(*, is_https: bool) -> list[tuple[str, str]]:
    """返回应注入到每个响应的 (header, value) 列表。

    ``is_https`` 取自请求是否经 TLS 终止代理（``X-Forwarded-Proto: https``）；仅在为真时附加 HSTS。
    """
    headers = list(_STATIC_SECURITY_HEADERS)
    if is_https:
        headers.append(_HSTS_HEADER)
    return headers
