#!/usr/bin/env bash
#
# render-agent-specs.sh — deploy-time 渲染 agent OpenAPI spec 的 servers 地址（D68 单一模型）。
#
# AgentRuntime 不解析 spec 内 ``${env:}``，故 ``agents/**/*.openapi.yaml`` 的 ``servers.url``
# 是字面量（committed = 本地 start-local 默认 http://127.0.0.1:8800）。跨容器部署时 AR 内
# agent 须经服务名回调（compose = http://zw-brain:8800）——本脚本按 ZW_BRAIN_REST_BASE_URL
# 把 servers.url 渲染成真实 zw-brain REST 地址。
#
# 用法：render-agent-specs.sh <agents_dir>
#   - ZW_BRAIN_REST_BASE_URL 未设 → 不改（保留 committed 默认，本地无害）。
#   - 幂等：可重复运行。只动 `- url: "http...`（servers 字面量），不碰其它。
set -euo pipefail

AGENTS_DIR="${1:-agents}"
BASE_URL="${ZW_BRAIN_REST_BASE_URL:-}"

if [[ -z "$BASE_URL" ]]; then
    echo "[render-agent-specs] ZW_BRAIN_REST_BASE_URL 未设，保留 spec 内 servers 默认值（不改）"
    exit 0
fi
if [[ ! -d "$AGENTS_DIR" ]]; then
    echo "[render-agent-specs] skip: agents dir 不存在：$AGENTS_DIR" >&2
    exit 0
fi

count=0
while IFS= read -r spec; do
    # 只替换 servers 下 `- url: "http..."` 的字面量；in-place（调用方保证目标可写，如运行副本）。
    if grep -qE '^[[:space:]]*-[[:space:]]*url:[[:space:]]*"http' "$spec"; then
        sed -i.bak -E "s#^([[:space:]]*-[[:space:]]*url:[[:space:]]*\")http[^\"]*(\")#\1${BASE_URL}\2#" "$spec"
        rm -f "$spec.bak"
        count=$((count + 1))
    fi
done < <(find "$AGENTS_DIR" -type f -name '*.openapi.yaml' 2>/dev/null)

echo "[render-agent-specs] ok: rendered $count openapi spec servers -> ${BASE_URL} (dir=${AGENTS_DIR})"
