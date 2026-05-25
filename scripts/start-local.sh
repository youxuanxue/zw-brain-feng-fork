#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

# 单一 canonical DB：`.data/zw_brain.db`。M0 一键导入（customer_acceptance_up.sh）
# 与日常 REST 写读用同一份；不再分裂为 customer_acceptance.db。
# 历史 customer_acceptance.db / 多次会话累积的 zw_brain.db 由 scripts/db-vacuum.sh
# 清理，由 preflight 段 18 监测膨胀。

REST_HOST="${ZW_BRAIN_REST_HOST:-127.0.0.1}"
REST_PORT="${ZW_BRAIN_REST_PORT:-8800}"
# K12 dashboard BFF 在二轮再砍中退役（详见 D15 二次反转）；本脚本仅启动 REST + WebUI

# Hard guard：start-local.sh 只用于 dev / 演示 box，绝不可用于客户 prod。
# 客户 prod 必须用 docker-image-deployment.md 路径起服务（IAF/OIDC 真接入）。
# 若调用方显式声明 prod 部署，立即拒启，避免下方 IAM bypass 误开。
DEPLOY_MODE="${ZW_BRAIN_DEPLOY_MODE:-dev}"
if [[ "$DEPLOY_MODE" == "prod" ]] || [[ "$DEPLOY_MODE" == "production" ]]; then
    echo "[start-local] FAIL: ZW_BRAIN_DEPLOY_MODE=$DEPLOY_MODE — start-local.sh 仅限 dev/演示，prod 请用 docker-image-deployment.md" >&2
    echo "[start-local] next-step: prod 部署见 docs/deployment/docker-image-deployment.md；本地 dev 跑：unset ZW_BRAIN_DEPLOY_MODE && bash scripts/start-local.sh" >&2
    exit 2
fi

# Local dev IAM bypass: skip IAF/OIDC so browser can log in immediately without
# external identity provider. NEVER set these in production — see
# docs/preflight-debt.md `dev-iam-bypass` entry. If caller has explicitly set
# ZW_BRAIN_IAF_AUTH_SERVER_URL we honour it (real IAF flow) and skip bypass.
# Same dev-mode: enable the WebUI role-switch dropdown so a single bypass user
# can exercise all 8 roles without separate IAM accounts. In prod the IAM
# integration provides real role mapping and this stays 0.
if [[ -z "${ZW_BRAIN_IAF_AUTH_SERVER_URL:-}" ]]; then
    export ZW_BRAIN_DEV_IAM_BYPASS="${ZW_BRAIN_DEV_IAM_BYPASS:-1}"
    export ZW_BRAIN_DEV_IAM_BYPASS_ACK="${ZW_BRAIN_DEV_IAM_BYPASS_ACK:-development-only}"
    export ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH="${ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH:-1}"
fi

REST_PID=""

cleanup() {
    local status=$?
    if [[ -n "$REST_PID" ]] && kill -0 "$REST_PID" 2>/dev/null; then
        kill "$REST_PID" 2>/dev/null || true
        wait "$REST_PID" 2>/dev/null || true
    fi
    exit "$status"
}
trap cleanup INT TERM EXIT

require_python() {
    if [[ ! -x "$PYTHON_BIN" ]]; then
        echo "[start-local] FAIL: missing virtualenv python at $PYTHON_BIN"
        echo "[start-local] Hint: create/install project deps in .venv first"
        exit 1
    fi
}

check_dependency() {
    "$PYTHON_BIN" -c "import sqlalchemy" >/dev/null
}

check_port_free() {
    local host="$1"
    local port="$2"
    "$PYTHON_BIN" - <<'PY' "$host" "$port"
import socket
import sys
host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket() as sock:
    sock.settimeout(1)
    code = sock.connect_ex((host, port))
    if code == 0:
        raise SystemExit(1)
raise SystemExit(0)
PY
}

show_port_conflict() {
    local port="$1"
    echo "[start-local] FAIL: port $port is already in use"
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
    fi
}

wait_for_health() {
    local url="$1"
    local label="$2"
    local attempts=40
    local i
    for ((i=1; i<=attempts; i++)); do
        if "$PYTHON_BIN" - <<'PY' "$url" >/dev/null 2>&1
import sys
import urllib.request

urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
urllib.request.urlopen(sys.argv[1], timeout=1).read()
PY
        then
            echo "[start-local] ok: $label healthy at $url"
            return 0
        fi
        sleep 0.5
    done
    echo "[start-local] FAIL: $label did not become healthy: $url"
    return 1
}

ensure_webui_build() {
    local dist_index="$REPO_ROOT/zw-brain-web/dist-vite/index.html"
    if [[ -f "$dist_index" ]]; then
        return 0
    fi
    if ! command -v npm >/dev/null 2>&1; then
        echo "[start-local] FAIL: zw-brain-web/dist-vite missing and npm not on PATH" >&2
        echo "[start-local] Hint: cd zw-brain-web && npm install && npm run build" >&2
        exit 1
    fi
    echo "[start-local] building zw-brain-web (dist-vite missing)..."
    (cd "$REPO_ROOT/zw-brain-web" && npm run build)
}

start_rest() {
    (
        cd "$REPO_ROOT"
        exec "$PYTHON_BIN" -m zw_brain.entry.rest.server
    ) &
    REST_PID=$!
}

echo "=== zw-brain local startup ==="
echo "[start-local] repo: $REPO_ROOT"
echo "[start-local] python: $PYTHON_BIN"

require_python
check_dependency

if ! check_port_free "$REST_HOST" "$REST_PORT"; then
    show_port_conflict "$REST_PORT"
    exit 1
fi

# F2：本机 dev 默认 mock 推理（须在 REST 子进程启动前 export）
if [[ -z "${ZW_BRAIN_INFERENCE_MODE:-}" ]]; then
    export ZW_BRAIN_INFERENCE_MODE=mock
fi

ensure_webui_build

start_rest

wait_for_health "http://$REST_HOST:$REST_PORT/health" "REST"

echo "[start-local] inference: ZW_BRAIN_INFERENCE_MODE=${ZW_BRAIN_INFERENCE_MODE} (mock=本机无网关; platform=需 INSPUR_INFERENCE_BASE_URL+API_KEY)"

# F11：本地 curl 502 常见原因是 shell 全局 http_proxy 把 127.0.0.1 也走代理
if [[ -n "${http_proxy:-}" || -n "${HTTP_PROXY:-}" || -n "${https_proxy:-}" || -n "${HTTPS_PROXY:-}" ]]; then
    echo "[start-local] tip: 检测到 http(s)_proxy；若 curl http://$REST_HOST:$REST_PORT 返回 502，请执行："
    echo "[start-local]       export NO_PROXY=127.0.0.1,localhost,\$NO_PROXY"
fi

echo "[start-local] REST PID: $REST_PID"
echo "[start-local] REST URL: http://$REST_HOST:$REST_PORT"
echo "[start-local] Press Ctrl+C to stop"

wait "$REST_PID"
