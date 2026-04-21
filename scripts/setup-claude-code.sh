#!/usr/bin/env bash
#
# Cursor 云端 Agent 环境下安装和配置 Claude Code CLI
#
# 使用场景：Cursor Long-running / Background Agent 需要在云端 VM 中
# 调用 claude -p 执行审查、拆解、校准等任务
#
# 前置条件：在 Cursor Dashboard → Cloud Agents → Secrets 中配置
#   ANTHROPIC_API_KEY=sk-ant-api03-...
#
# 用法：
#   bash scripts/setup-claude-code.sh          # 安装 + 检查
#   bash scripts/setup-claude-code.sh --check  # 仅检查，不安装
#   source scripts/setup-claude-code.sh        # 安装 + 导出环境变量到当前 shell

set -euo pipefail

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
fi

status_ok=0
status_fail=0

check() {
    local label="$1"
    local result="$2"
    if [[ "$result" == "ok" ]]; then
        echo "  [ok] $label"
        ((status_ok++))
    else
        echo "  [!!] $label — $result"
        ((status_fail++))
    fi
}

echo "=== Claude Code CLI Setup ==="
echo ""

# --- 1. Node.js ---
if command -v node &>/dev/null; then
    check "Node.js" "ok"
else
    check "Node.js" "未安装，Claude Code CLI 需要 Node.js >= 18"
    if [[ "$CHECK_ONLY" == false ]]; then
        echo "  ... 尝试通过 nvm 或系统包管理器安装 Node.js"
        if command -v nvm &>/dev/null; then
            nvm install --lts
        elif command -v apt-get &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq nodejs npm
        else
            echo "  ... 无法自动安装 Node.js，请手动安装"
            exit 1
        fi
    fi
fi

# --- 2. Claude Code CLI ---
if command -v claude &>/dev/null; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    check "Claude Code CLI" "ok"
    echo "       版本: $CLAUDE_VERSION"
else
    check "Claude Code CLI" "未安装"
    if [[ "$CHECK_ONLY" == false ]]; then
        echo "  ... 正在安装 Claude Code CLI"
        npm install -g @anthropic-ai/claude-code
        if command -v claude &>/dev/null; then
            CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
            echo "  [ok] 安装成功，版本: $CLAUDE_VERSION"
            ((status_ok++))
            ((status_fail--))
        else
            echo "  [!!] 安装失败"
            exit 1
        fi
    fi
fi

# --- 3. ANTHROPIC_API_KEY ---
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    KEY_PREFIX="${ANTHROPIC_API_KEY:0:10}..."
    check "ANTHROPIC_API_KEY" "ok"
    echo "       前缀: $KEY_PREFIX"
else
    # Cursor Cloud Agent 的 Secrets 可能不在 printenv 中显示，
    # 但对 claude CLI 进程可用。尝试通过 claude 本身验证。
    if [[ "$CHECK_ONLY" == false ]] && command -v claude &>/dev/null; then
        echo "  ... ANTHROPIC_API_KEY 未在 shell 环境中检测到"
        echo "  ... 尝试通过 claude CLI 验证（Cursor Secrets 可能直接注入进程）"
        if claude -p "echo ok" --max-turns 1 --max-budget-usd 0.01 &>/dev/null 2>&1; then
            check "ANTHROPIC_API_KEY" "ok"
            echo "       (通过 Cursor Secrets 注入，shell 中不可见但 claude 可用)"
        else
            check "ANTHROPIC_API_KEY" "未配置"
            echo ""
            echo "  配置方法（选择一种）："
            echo ""
            echo "  方法 1: Cursor Dashboard（推荐，云端 Agent 专用）"
            echo "    1. 打开 https://cursor.com/dashboard/cloud-agents"
            echo "    2. Secrets → Add Secret"
            echo "    3. Name: ANTHROPIC_API_KEY"
            echo "    4. Value: sk-ant-api03-..."
            echo "    5. 重启 Cloud Agent 生效"
            echo ""
            echo "  方法 2: 本地 shell（仅限本地执行）"
            echo "    export ANTHROPIC_API_KEY=sk-ant-api03-..."
            echo ""
        fi
    else
        check "ANTHROPIC_API_KEY" "未配置（--check 模式，跳过验证）"
    fi
fi

# --- 4. 项目上下文 ---
if [[ -f "CLAUDE.md" ]]; then
    check "CLAUDE.md" "ok"
else
    check "CLAUDE.md" "未找到项目级 CLAUDE.md"
fi

if [[ -d "docs/approved" ]]; then
    APPROVED_COUNT=$(ls docs/approved/*.md docs/approved/*.yaml 2>/dev/null | wc -l | tr -d ' ')
    check "docs/approved/" "ok"
    echo "       审批产物: ${APPROVED_COUNT} 个文件"
else
    check "docs/approved/" "目录不存在（首次使用时由 Agent 在 GATE-1 PR 中创建）"
fi

# --- Summary ---
echo ""
echo "=== 结果: ${status_ok} 通过, ${status_fail} 需处理 ==="

if [[ $status_fail -gt 0 ]]; then
    exit 1
fi
