"""数据直达报文签名（接口规范 v0.55 §5 + 附录C）。

签名 = ``base64(HmacSHA256(gjzwfwpt_sid + gjzwfwpt_rid + gjzwfwpt_rtime, appsecret))``。
文档附录C 的 POSTMAN 示例：``textToSign = serviceId + rid + timestamp``（serviceId 即 sid），
``signature = HmacSHA256(textToSign, appSecret).toString(Base64)``。本模块是该算法的 Python 实现，
纯函数、可单测（固定输入 → 固定签名向量），不触网络、不读环境。
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def sign_request(sid: str, rid: str, rtime: str, appsecret: str) -> str:
    """计算 ``gjzwfwpt_sign``。

    入参均为字符串（rtime 是毫秒时间戳的字符串形式，见 envelope）。拼接顺序严格为
    sid + rid + rtime —— 与国家平台校验侧一致，顺序错即验签失败。
    """
    text_to_sign = f"{sid}{rid}{rtime}".encode()
    digest = hmac.new(appsecret.encode(), text_to_sign, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")
