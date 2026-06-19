#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 自动加载 .env（若存在）：cp .env.example .env 填好即可一键起。
# 安全加载——只导出 KEY=VALUE 行，跳过注释/空行，不 source 执行（半填的占位 `<...>` 不会炸）。
# 已存在的 shell 环境变量优先（不覆盖显式 export），与下方 ${VAR:-default} 语义一致。
if [ -f "$REPO_ROOT/.env" ]; then
    while IFS='=' read -r _envk _envv; do
        case "$_envk" in ''|'#'*) continue ;; esac
        # 剥行内 ` # 注释` + 尾随空白：否则注释/空白混进值（如 URL 末尾），连接报控制字符。
        # 仅剥"空白+#"（真注释），不动 a#b 这类值内 #。
        _envv=$(printf '%s' "$_envv" | sed -E 's/[[:space:]]+#.*$//; s/[[:space:]]+$//')
        # 已在环境里的变量优先（不覆盖显式 export / CLI 传入）；printenv 在 bash 3.2 下安全
        printenv "$_envk" >/dev/null 2>&1 || export "$_envk=$_envv"
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$REPO_ROOT/.env")
    unset _envk _envv
fi

# 默认 .venv/bin/python；可用 ZW_BRAIN_PYTHON_BIN 切换到其它解释器
# （例如本机要跑 AgentRuntime 全链路时切到 .venv-py312/bin/python — vendor wheel 是 py312-only）
PYTHON_BIN="${ZW_BRAIN_PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

# 运行时后端 = PostgreSQL（zw_brain/shared/db.py DEFAULT_PG_URL；已全盘 PG）。
#   docker compose up -d postgres   # 起库（凭据/端口与默认 URL 对齐，零 env）
#   bash scripts/start-local.sh      # 无 env 即默认连本库
# 想连别的库：export ZW_BRAIN_DATABASE_URL=...（唯一覆盖旋钮，须为 PostgreSQL）。
# 设 ZW_BRAIN_LOCAL_PG_AUTOUP=1 让本脚本自动 docker compose up。

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
    # dev 走查会话所属机构默认 = 省大数据局（sd-default 枢纽机构、seed 资源主提供方）。
    # R11 方向 guard 对 owner_org_code fail-closed：会话 org 与资源提供方一致，
    # 有条件二级部门审核（application.dept_approve）在本机走查 / e2e 才可走通。
    export ZW_BRAIN_DEV_IAM_BYPASS_ORG="${ZW_BRAIN_DEV_IAM_BYPASS_ORG:-11370000MB284651XL}"
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
    # PostgreSQL 后端需 psycopg 驱动。
    if [[ "$DB_URL" == postgresql* ]]; then
        if ! "$PYTHON_BIN" -c "import psycopg" >/dev/null 2>&1; then
            echo "[start-local] FAIL: 后端是 PostgreSQL，但缺 psycopg 驱动" >&2
            echo "[start-local] Hint: uv pip install -e '.[postgres]'" >&2
            exit 1
        fi
    fi
}

# 解析 get_database_url() 的真实结果（含 env 覆盖优先级），供下游分支判断后端类型。
resolve_db_url() {
    DB_URL="$("$PYTHON_BIN" -c 'from zw_brain.shared.db import get_database_url; print(get_database_url())')"
}

# 默认 PG 路径：探活 host:port；不通则 fail-fast 给确切命令。设 AUTOUP=1 自动 compose up。
ensure_postgres_ready() {
    [[ "$DB_URL" == postgresql* ]] || return 0
    local hostport
    hostport="$("$PYTHON_BIN" - "$DB_URL" <<'PY'
import sys
from urllib.parse import urlsplit
u = urlsplit(sys.argv[1])
print(f"{u.hostname or '127.0.0.1'} {u.port or 5432}")
PY
)"
    local pg_host pg_port
    read -r pg_host pg_port <<<"$hostport"
    if check_port_free "$pg_host" "$pg_port"; then
        # 端口空 = PG 没在监听
        if [[ "${ZW_BRAIN_LOCAL_PG_AUTOUP:-0}" == "1" ]] && command -v docker >/dev/null 2>&1; then
            echo "[start-local] PG 未就绪，ZW_BRAIN_LOCAL_PG_AUTOUP=1 → docker compose up -d postgres"
            (cd "$REPO_ROOT" && docker compose up -d postgres)
        else
            echo "[start-local] FAIL: 默认后端 PostgreSQL 未就绪（$pg_host:$pg_port 无监听）" >&2
            echo "[start-local] Hint: docker compose up -d postgres" >&2
            echo "[start-local] Hint: 自动起库可设 ZW_BRAIN_LOCAL_PG_AUTOUP=1 重跑本脚本" >&2
            exit 1
        fi
    fi
    # 等到能连上（compose 刚拉起需等 healthcheck）。
    local i
    for ((i=1; i<=40; i++)); do
        check_port_free "$pg_host" "$pg_port" || { echo "[start-local] ok: PG 就绪 $pg_host:$pg_port"; return 0; }
        sleep 0.5
    done
    echo "[start-local] FAIL: PG 在 $pg_host:$pg_port 未在超时内就绪" >&2
    exit 1
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
    local dist_path="$REPO_ROOT/zw-brain-web/dist-vite"
    local dist_index="$dist_path/index.html"
    # F-001 防御：worktree 切换 / 历史会话残留可能在 zw-brain-web/dist-vite 留下
    # 指向已删 worktree 的 dangling symlink。vite/rollup 写产物时 follow 这个链接
    # 会 ENOENT，错误信息却指向 closeBundle 钩子，定位困难。任何形态的符号链接
    # 这里都不可信（即便它指向其它有效 worktree，build 写入另一个 worktree 也是
    # 混乱），统一 rm 让 vite 在 build 时新建真实目录。
    if [[ -L "$dist_path" ]]; then
        echo "[start-local] removing pre-existing dist-vite symlink (worktree leftover)"
        rm "$dist_path"
    fi
    local needs_build=0
    if [[ ! -f "$dist_index" ]]; then
        needs_build=1
    elif find "$REPO_ROOT/zw-brain-web/src" -type f -newer "$dist_index" -print -quit 2>/dev/null | grep -q .; then
        needs_build=1
    fi
    if [[ "$needs_build" -eq 0 ]]; then
        return 0
    fi
    if ! command -v npm >/dev/null 2>&1; then
        echo "[start-local] FAIL: zw-brain-web/dist-vite stale/missing and npm not on PATH" >&2
        echo "[start-local] Hint: cd zw-brain-web && npm install && npm run build" >&2
        exit 1
    fi
    if [[ -f "$dist_index" ]]; then
        echo "[start-local] rebuilding zw-brain-web (src newer than dist-vite)..."
    else
        echo "[start-local] building zw-brain-web (dist-vite missing)..."
    fi
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
resolve_db_url
check_dependency
# 打印时剥掉 user:pass@（凭据不进日志），只留方言 + host/库。
if [[ "$DB_URL" == *@* ]]; then
    echo "[start-local] db: ${DB_URL%%://*}://${DB_URL##*@}"
else
    echo "[start-local] db: $DB_URL"
fi

if ! check_port_free "$REST_HOST" "$REST_PORT"; then
    show_port_conflict "$REST_PORT"
    exit 1
fi

ensure_postgres_ready

# F2：本机 dev 默认 mock 推理（须在 REST 子进程启动前 export）
if [[ -z "${ZW_BRAIN_INFERENCE_MODE:-}" ]]; then
    export ZW_BRAIN_INFERENCE_MODE=mock
fi

# 排障日志落盘：本机默认 .data/logs（已 gitignore），文件侧恒为 JSON lines；
# 容器场景不设此变量、走 stdout 收集。应用自己写文件并轮转，脚本不 tee。
export ZW_BRAIN_LOG_DIR="${ZW_BRAIN_LOG_DIR:-$REPO_ROOT/.data/logs}"
mkdir -p "$ZW_BRAIN_LOG_DIR"

ensure_webui_build

start_rest

wait_for_health "http://$REST_HOST:$REST_PORT/health" "REST"

echo "[start-local] inference: ZW_BRAIN_INFERENCE_MODE=${ZW_BRAIN_INFERENCE_MODE} (mock=本机无网关; platform=需 ZW_BRAIN_INFERENCE_GATEWAY_URL+API_KEY)"

# F11：本地 curl 502 常见原因是 shell 全局 http_proxy 把 127.0.0.1 也走代理
if [[ -n "${http_proxy:-}" || -n "${HTTP_PROXY:-}" || -n "${https_proxy:-}" || -n "${HTTPS_PROXY:-}" ]]; then
    echo "[start-local] tip: 检测到 http(s)_proxy；若 curl http://$REST_HOST:$REST_PORT 返回 502，请执行："
    echo "[start-local]       export NO_PROXY=127.0.0.1,localhost,\$NO_PROXY"
fi

echo "[start-local] REST PID: $REST_PID"
echo "[start-local] REST URL: http://$REST_HOST:$REST_PORT"
echo "[start-local] logs: $ZW_BRAIN_LOG_DIR/rest.log  (排障: tail -f | jq .，按 X-Request-Id grep 串全链)"
echo "[start-local] Press Ctrl+C to stop"

wait "$REST_PID"
