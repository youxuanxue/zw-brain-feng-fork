#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
REST_HOST="${ZW_BRAIN_REST_HOST:-127.0.0.1}"
REST_PORT="${ZW_BRAIN_REST_PORT:-8800}"
DASHBOARD_HOST="${ZW_BRAIN_DASHBOARD_BFF_HOST:-127.0.0.1}"
DASHBOARD_PORT="${ZW_BRAIN_DASHBOARD_BFF_PORT:-8801}"
REST_PID=""
DASHBOARD_PID=""

cleanup() {
    local status=$?
    if [[ -n "$REST_PID" ]] && kill -0 "$REST_PID" 2>/dev/null; then
        kill "$REST_PID" 2>/dev/null || true
        wait "$REST_PID" 2>/dev/null || true
    fi
    if [[ -n "$DASHBOARD_PID" ]] && kill -0 "$DASHBOARD_PID" 2>/dev/null; then
        kill "$DASHBOARD_PID" 2>/dev/null || true
        wait "$DASHBOARD_PID" 2>/dev/null || true
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

start_rest() {
    (
        cd "$REPO_ROOT"
        exec "$PYTHON_BIN" -m zw_brain.entry.rest.server
    ) &
    REST_PID=$!
}

start_dashboard() {
    (
        cd "$REPO_ROOT"
        exec "$PYTHON_BIN" zw-brain-dashboard/bff/main.py
    ) &
    DASHBOARD_PID=$!
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

if ! check_port_free "$DASHBOARD_HOST" "$DASHBOARD_PORT"; then
    show_port_conflict "$DASHBOARD_PORT"
    exit 1
fi

start_rest
start_dashboard

wait_for_health "http://$REST_HOST:$REST_PORT/health" "REST"
wait_for_health "http://$DASHBOARD_HOST:$DASHBOARD_PORT/health" "Dashboard"

echo "[start-local] REST PID: $REST_PID"
echo "[start-local] Dashboard PID: $DASHBOARD_PID"
echo "[start-local] REST URL: http://$REST_HOST:$REST_PORT"
echo "[start-local] Dashboard URL: http://$DASHBOARD_HOST:$DASHBOARD_PORT"
echo "[start-local] Press Ctrl+C to stop both services"

wait "$REST_PID" "$DASHBOARD_PID"
