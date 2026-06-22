#!/usr/bin/env bash
#
# 独立 AgentRuntime 容器 entrypoint（D68 单一模型）。
# agents/ 作为「单一源」由 compose 以只读卷挂在 /srv/agents-src；本脚本拷到可写 /app/agents、
# 按 ZW_BRAIN_REST_BASE_URL 渲染 openapi servers（AR 内 agent 回调 zw-brain 的真实地址），
# 再 exec 真正的 serve 命令。无源挂载时直接用镜像内置 /app/agents（build COPY）。
set -euo pipefail

if [[ -d /srv/agents-src ]]; then
    mkdir -p /app/agents
    cp -rf /srv/agents-src/. /app/agents/
    echo "[ar-entrypoint] synced agents from read-only source mount /srv/agents-src → /app/agents"
fi

# 渲染 openapi servers（ZW_BRAIN_REST_BASE_URL 未设则保留 committed 默认，无害）。
/usr/local/bin/render-agent-specs.sh /app/agents || true

exec "$@"
