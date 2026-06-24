#!/usr/bin/env bash
#
# A5' 一键脚本：在 zw-brain 仓库根目录创建 .venv-py312 并装齐 AgentRuntime 全链路依赖。
#
# 触发场景：本机要跑 AgentRuntime（Embedded SDK / validate / doctor / REST 任务接口）
#   时，vendor 离线包是 py312-only；默认 .venv 多为 py3.13，import agent_runtime 会失败。
#   本脚本一次性把 py312 venv + 项目 -e .[dev] + vendor wheel 全部装好，
#   配合 start-local.sh 的 ZW_BRAIN_PYTHON_BIN 覆盖就能跑全链路。
#
# 用法：
#   bash scripts/setup-py312-venv.sh           # 全量安装（已存在 .venv-py312 时 skip 创建）
#   bash scripts/setup-py312-venv.sh --check   # 仅检查现状，不修改
#   bash scripts/setup-py312-venv.sh --force   # 删掉旧 .venv-py312 重建
#
# 安装成功后，启动 REST 全链路：
#   export ZW_BRAIN_PYTHON_BIN="$PWD/.venv-py312/bin/python"
#   export ZW_BRAIN_AGENT_RUNTIME_ENABLED=1
#   bash scripts/start-local.sh
#
# 不做：
#   * 不动 .venv（py3.13 主 venv 保持原样，pytest / preflight 走它）
#   * 不写 shell profile（用户自己决定怎么持久化 ZW_BRAIN_PYTHON_BIN）
#   * 不装模型网关 secrets（见 .env.example 的 AgentRuntime OPENAI_COMPATIBLE_* 段）

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VENV_DIR=".venv-py312"
PYTHON_TARGET_MINOR="3.12"
VENDOR_DIR="vendor/agent-runtime"
VENDOR_RELEASE_DIR="$VENDOR_DIR/release/v1.1.3"
VENDOR_TARBALL="$VENDOR_RELEASE_DIR/agent-runtime-1.1.3-py312-pyc-only.tar.gz"
VENDOR_SHA256="$VENDOR_TARBALL.sha256"
VENDOR_EXTRACT_DIRNAME="agent-runtime-1.1.3-py312-pyc-only"
VENDOR_EXTRACT_DIR="$VENDOR_RELEASE_DIR/$VENDOR_EXTRACT_DIRNAME"
DEEPAGENTS_REQS="$VENDOR_DIR/requirements-deepagents.txt"

CHECK_ONLY=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        --force) FORCE=1 ;;
        -h|--help)
            sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "[setup-py312] unknown arg: $arg (try --help)" >&2
            exit 2
            ;;
    esac
done

ok_count=0
fail_count=0
log_ok() { echo "  [ok] $1"; ok_count=$((ok_count + 1)); }
log_warn() { echo "  [warn] $1"; }
log_fail() { echo "  [fail] $1" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "=== $1 ==="; }

# ── 1. 前置：uv + vendor 包 + sha256 ─────────────────────────────
section "1. 前置检查"

if ! command -v uv >/dev/null 2>&1; then
    log_fail "uv 未安装 — pyproject.toml 与 sd-default-onboarding.md 强制走 uv"
    echo "      install: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
else
    log_ok "uv $(uv --version | awk '{print $2}') 在 PATH 上"
fi

if [[ ! -f "$VENDOR_TARBALL" ]]; then
    log_fail "vendor 离线包不存在: $VENDOR_TARBALL"
else
    log_ok "vendor tarball: $VENDOR_TARBALL"
fi

if [[ ! -f "$VENDOR_SHA256" ]]; then
    log_fail "vendor sha256 校验文件不存在: $VENDOR_SHA256"
else
    if (cd "$VENDOR_RELEASE_DIR" && shasum -a 256 -c "$(basename "$VENDOR_SHA256")" >/dev/null 2>&1); then
        log_ok "vendor sha256 校验通过"
    else
        log_fail "vendor sha256 校验失败 — 包损坏或被改，禁止安装"
    fi
fi

if [[ ! -f "$DEEPAGENTS_REQS" ]]; then
    log_fail "$DEEPAGENTS_REQS 不存在（vendor README 引用的依赖清单丢失）"
else
    log_ok "deepagents requirements 存在"
fi

if [[ "$fail_count" -gt 0 ]]; then
    echo
    echo "[setup-py312] 前置检查失败，停止。" >&2
    exit 1
fi

# ── 2. .venv-py312 现状 ─────────────────────────────────────────
section "2. .venv-py312 现状"

venv_exists=0
venv_is_py312=0
if [[ -d "$VENV_DIR" ]]; then
    venv_exists=1
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        actual_minor=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
        if [[ "$actual_minor" == "$PYTHON_TARGET_MINOR" ]]; then
            log_ok ".venv-py312 已存在且 Python $actual_minor"
            venv_is_py312=1
        else
            log_warn ".venv-py312 存在但 Python=$actual_minor（期望 $PYTHON_TARGET_MINOR）"
        fi
    else
        log_warn ".venv-py312 存在但无 bin/python — 视为损坏"
    fi
else
    log_warn ".venv-py312 不存在"
fi

# ── 3. 已装依赖现状（仅在 venv 是 py312 时有意义） ────────────────
section "3. 已装依赖现状"

agent_runtime_importable=0
zw_brain_importable=0
if [[ "$venv_is_py312" -eq 1 ]]; then
    if "$VENV_DIR/bin/python" -c "import agent_runtime" >/dev/null 2>&1; then
        log_ok "import agent_runtime: ok"
        agent_runtime_importable=1
    else
        log_warn "import agent_runtime 失败"
    fi
    if "$VENV_DIR/bin/python" -c "import zw_brain" >/dev/null 2>&1; then
        log_ok "import zw_brain: ok"
        zw_brain_importable=1
    else
        log_warn "import zw_brain 失败"
    fi
else
    echo "  (skip — venv 非 py312)"
fi

# ── 4. --check 短路 ─────────────────────────────────────────────
if [[ "$CHECK_ONLY" -eq 1 ]]; then
    section "结果（--check 模式）"
    if [[ "$venv_is_py312" -eq 1 && "$agent_runtime_importable" -eq 1 && "$zw_brain_importable" -eq 1 ]]; then
        echo "  [ok] AgentRuntime 全链路就绪。下一步："
        echo "       export ZW_BRAIN_PYTHON_BIN=\"$REPO_ROOT/$VENV_DIR/bin/python\""
        echo "       export ZW_BRAIN_AGENT_RUNTIME_ENABLED=1"
        echo "       bash scripts/start-local.sh"
        exit 0
    fi
    echo "  [fail] 全链路未就绪。去掉 --check 重新执行本脚本即可一次装齐。"
    exit 1
fi

# ── 5. 创建 / 重建 .venv-py312 ───────────────────────────────────
section "5. 创建 .venv-py312"

recreate=0
if [[ "$FORCE" -eq 1 && "$venv_exists" -eq 1 ]]; then
    echo "  --force：删除旧 $VENV_DIR"
    rm -rf "$VENV_DIR"
    venv_exists=0
    venv_is_py312=0
    recreate=1
elif [[ "$venv_exists" -eq 1 && "$venv_is_py312" -eq 0 ]]; then
    echo "  现有 $VENV_DIR 非 py312，删除重建"
    rm -rf "$VENV_DIR"
    venv_exists=0
    recreate=1
fi

if [[ "$venv_exists" -eq 0 ]]; then
    echo "  uv venv --python $PYTHON_TARGET_MINOR $VENV_DIR  (uv 会自动下载 py312)"
    uv venv --python "$PYTHON_TARGET_MINOR" "$VENV_DIR"
    venv_is_py312=1
    log_ok "$VENV_DIR 已创建"
elif [[ "$recreate" -eq 0 ]]; then
    log_ok "复用现有 $VENV_DIR"
fi

VENV_PY="$REPO_ROOT/$VENV_DIR/bin/python"

# ── 6. 装 zw-brain 自身 + dev extras ─────────────────────────────
section "6. 装 zw-brain 自身（-e .[dev]）"
uv pip install --python "$VENV_PY" -e ".[dev]"
log_ok "zw-brain + dev extras 已装"

# ── 7. 解包 vendor tar.gz 并装 agent-runtime 全链路 ──────────────
section "7. 解包 vendor wheel 并安装"

if [[ -d "$VENDOR_EXTRACT_DIR" ]]; then
    echo "  vendor 解压目录已存在，覆盖重解压：$VENDOR_EXTRACT_DIR"
    rm -rf "$VENDOR_EXTRACT_DIR"
fi
(cd "$VENDOR_RELEASE_DIR" && tar -xzf "$(basename "$VENDOR_TARBALL")")
log_ok "vendor 已解压至 $VENDOR_EXTRACT_DIR"

if [[ ! -f "$VENDOR_EXTRACT_DIR/requirements.txt" ]]; then
    log_fail "解压目录缺 requirements.txt（vendor 包结构异常）"
    exit 1
fi
if [[ ! -x "$VENDOR_EXTRACT_DIR/install.sh" ]]; then
    log_fail "解压目录缺可执行 install.sh（vendor 包结构异常）"
    exit 1
fi

echo "  uv pip install vendor requirements.txt + deepagents requirements"
uv pip install --python "$VENV_PY" \
    -r "$VENDOR_EXTRACT_DIR/requirements.txt" \
    -r "$DEEPAGENTS_REQS"

echo "  运行 vendor 自带 install.sh（在 venv 内）"
# install.sh 调用 python / pip；放进 venv 路径前缀，避免落到系统 Python
(cd "$VENDOR_EXTRACT_DIR" && PATH="$REPO_ROOT/$VENV_DIR/bin:$PATH" VIRTUAL_ENV="$REPO_ROOT/$VENV_DIR" ./install.sh)

log_ok "vendor agent-runtime 已安装"

# ── 8. 烟测 ──────────────────────────────────────────────────────
section "8. 烟测"

"$VENV_PY" -c "from agent_runtime import RuntimeService; print('  agent_runtime import: ok')"
"$VENV_PY" -c "import zw_brain; print('  zw_brain import: ok')"
if "$VENV_PY" scripts/agentruntime_validate.py agents/a_zw_search_helper/AGENT.yaml >/dev/null 2>&1; then
    log_ok "agentruntime_validate.py (a_zw_search_helper): ok"
else
    log_fail "agentruntime_validate.py 报错 — 重跑去掉 >/dev/null 看详情"
fi

# 确定性自动化运营和运维：silent-failure 防御 — §8 烟测若有 fail 必须中止，
# 不得让 §9 段对用户打印「全链路就绪」。同脚本 §1 (line 96-100) 已是同款模式。
if [[ "$fail_count" -gt 0 ]]; then
    echo
    echo "[setup-py312] FAIL: $fail_count smoke test(s) failed — 全链路未就绪" >&2
    exit 1
fi

# ── 9. 收尾：下一步 ──────────────────────────────────────────────
section "完成"
cat <<EOF
  AgentRuntime 全链路本机回放就绪。

  下一步（启动 REST + WebUI + 独立 AgentRuntime 全链路）：
    export ZW_BRAIN_PYTHON_BIN="$REPO_ROOT/$VENV_DIR/bin/python"
    export ZW_BRAIN_AGENT_RUNTIME_MODE=http ZW_BRAIN_AGENT_RUNTIME_ENABLED=1
    # 模型网关 secrets 见 .env.example 的 AgentRuntime OPENAI_COMPATIBLE_* 段
    bash scripts/start-local.sh

  日常 pytest / preflight 继续走主 .venv（py3.13），无需切换。
  二次确认：bash scripts/setup-py312-venv.sh --check
EOF
