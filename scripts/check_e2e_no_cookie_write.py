#!/usr/bin/env python3
"""check_e2e_no_cookie_write.py — e2e 写 /api/skills 必走无 cookie 上下文（防 CSRF 假覆盖回潮）。

为什么需要这道守卫：
    后端 CSRF 双提交是签字安全设计（PR#53，生产侧正确）。其门控按 **HTTP 方法**判定——
    `zw_brain/entry/rest/server.py` 的 `_method_requires_csrf()` 对 cookie 会话下的任何
    POST/PUT/PATCH/DELETE 都强制校验 X-CSRF 令牌（不区分读写 skill）。

    Playwright 的 `page.request` **复用浏览器登录 cookie**：直接
    `page.request.post('/api/skills/<skill>')` 命中「有 cookie 会话」却不附令牌 →
    必返 403 `csrf_token_invalid` → setup 造数据失败 → 测试假 skip / 假覆盖（绿但没真跑）。

    正确范式 = **无 cookie 的独立 APIRequestContext**：
        const api = await playwright.request.newContext();
        await api.post(`${E2E_BASE_URL}/api/skills/<skill>`, { data: { role: 'ROLE_X', ... } });
    无 cookie → 命中 server 的 dev-bypass Path 2（role 从 body 取、不校验 CSRF）。
    参照现成实现：tests/e2e/permission_matrix_walkthrough.spec.ts / d57_permission_batch.spec.ts。

判定模型（刻意简单、确定性）：
    逐行扫 tests/e2e/**.ts，禁 `page.request.(post|put|patch|delete)(`，且其调用实参
    （写调用行 + 紧邻 2 行的窗口，容 formatter 把长 URL 换行）指向 `/api/skills/`。
    宁可过覆盖 + `// csrf-ok:` 豁免，不可「同行匹配」漏掉多行写调用（防回潮 guard 不漏为先）。
    - 不误伤：只锚 `page.request.`（带浏览器 cookie 的那个）；无 cookie 的 `request.post`（内置
      request fixture）/ `api.post`（newContext）不匹配；`page.request.get`（读，GET 不门控 CSRF）不匹配。
    - 豁免：命中行或其上一行含 `// csrf-ok: <理由>` 放行（带理由的真特例兜底）。

退出码：0 = 全部通过；非零 = 至少一处违规（打印 文件:行）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
E2E_DIR = REPO / "tests" / "e2e"

# 仅匹配 page.request 的写方法（带 cookie 的浏览器上下文）。
# `request.post` / `api.post`（无 cookie）、`page.request.get`（读）刻意不匹配。
WRITE_CALL = re.compile(r"\bpage\.request\.(?:post|put|patch|delete)\s*\(")
SKILLS_REF = "/api/skills/"
EXEMPT = "// csrf-ok:"


def violations() -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    if not E2E_DIR.is_dir():
        return hits
    for path in sorted(E2E_DIR.rglob("*.ts")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not WRITE_CALL.search(line):
                continue
            # URL 实参可与 .post( 同行、也可能被 formatter 换行到紧邻行 → 看「写调用行 + 后 2 行」窗口，
            # 避免「同行匹配」被多行调用绕过（漏覆盖比误报更伤防回潮 guard；误报有 // csrf-ok: 兜底）。
            window = "\n".join(lines[i : i + 3])
            if SKILLS_REF not in window:
                continue
            if EXEMPT in line or (i > 0 and EXEMPT in lines[i - 1]):
                continue
            hits.append((path, i + 1, line.strip()))
    return hits


def main() -> int:
    hits = violations()
    if not hits:
        print("[check-e2e-no-cookie-write] ok: 无『带 cookie 的 page.request 写 /api/skills』违规")
        return 0
    print(
        "[check-e2e-no-cookie-write] FAIL: 带 cookie 的 page.request 写 /api/skills 会命中后端 CSRF → 403 假覆盖。"
    )
    print(
        "  改走无 cookie 独立上下文：const api = await playwright.request.newContext();"
        " await api.post('/api/skills/<skill>', { data: { role, ... } });（role 走 body）"
    )
    print("  读路径用 page.request.get 合法；确有特例在命中行或上一行加 `// csrf-ok: <理由>` 豁免。")
    for path, lineno, text in hits:
        print(f"  {path.relative_to(REPO)}:{lineno}: {text}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
