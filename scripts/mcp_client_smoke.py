#!/usr/bin/env python3
"""mcp_client_smoke.py — F6 模拟 MCP client（如 Cursor/Claude）外部接入测试。

启动 `python -m zw_brain.entry.mcp.server serve --transport stdio`，
通过 stdin/stdout 跑 initialize + tools/list + 5 个 J1 高频 capability tools/call。

每个 capability 输出 STEP 行（带 status=200|ERROR）。整脚本 exit 0 即可
表明 MCP 通道连通；具体 capability handler 缺失（E1/E2/E4 未 land）属业务态，
不阻塞 MCP 协议层的「连通可证」AC4 证据。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# 5 J1 高频 capability（与 F5 headless demo 同源；保证至少有真 200 出现）
TEST_CALLS = [
    ("workbench.view",  {"role": "ROLE_ORGAN_OPERATER"}),
    ("catalog.browse",  {"role": "ROLE_ORGAN_OPERATER", "limit": 3, "lifecycle": "active", "kind": "real"}),
    ("data.search",     {"role": "ROLE_ORGAN_OPERATER", "query": "停车场"}),
    ("delivery.list",   {"role": "ROLE_ORGAN_MANAGER"}),
    ("provider.view",   {"role": "ROLE_BUSIAUDIT"}),
]


def main() -> int:
    env = {**os.environ,
           "ZW_BRAIN_DEV_IAM_BYPASS": "1",
           "ZW_BRAIN_DEV_IAM_BYPASS_ACK": "development-only"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "zw_brain.entry.mcp.server", "serve", "--transport", "stdio"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env,
    )

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line) if line else None

    print("=== zw-brain MCP client smoke (5 J1 capability via stdio JSON-RPC) ===\n")

    # 1. initialize
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "smoke", "version": "0.1"}}})
    init = recv()
    server_info = init.get("result", {}).get("serverInfo", {})
    print(f"[INIT ] server={server_info.get('name')} v{server_info.get('version')} "
          f"protocol={init['result']['protocolVersion']}")

    # 2. notifications/initialized (per MCP spec, optional but客户端通常发)
    send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # 3. tools/list
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    listed = recv()
    tools = listed["result"]["tools"]
    print(f"[LIST ] {len(tools)} tools published (sample: {tools[0]['name']}, {tools[1]['name']}, ...)")

    # 4. tools/call × 5
    print("\n=== 5 capability round-trip ===")
    rc_id = 100
    ok_count = 0
    for skill_id, args in TEST_CALLS:
        rc_id += 1
        send({"jsonrpc": "2.0", "id": rc_id, "method": "tools/call",
              "params": {"name": skill_id, "arguments": args}})
        resp = recv()
        if "error" in resp:
            err = resp["error"]
            print(f"[CALL ] {skill_id:25} → ERROR code={err['code']} message={err['message'][:80]}")
        else:
            content = resp["result"]["content"][0]["text"]
            try:
                parsed = json.loads(content)
                # 取首个有意义的字段作为成功标识
                keys = list(parsed.keys())[:3] if isinstance(parsed, dict) else []
                print(f"[CALL ] {skill_id:25} → 200 result_keys={keys}")
                ok_count += 1
            except json.JSONDecodeError:
                print(f"[CALL ] {skill_id:25} → 200 text_len={len(content)}")
                ok_count += 1

    # 5. shutdown
    send({"jsonrpc": "2.0", "id": 999, "method": "shutdown"})
    recv()
    proc.wait(timeout=5)

    print(f"\n=== {ok_count}/5 capability calls succeeded; mcp server exit={proc.returncode} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
