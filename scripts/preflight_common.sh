#!/usr/bin/env bash
#
# zw-brain: vendored generic preflight (fork of dev-rules template).
# Approved-doc + stat checks use scripts/ in this repo so CI needs no dev-rules checkout.
#
# 用法：由 scripts/preflight.sh 调用；也可单独调试。

set -u

if [ -n "${PREFLIGHT_REPO_ROOT:-}" ] && [ -d "$PREFLIGHT_REPO_ROOT" ]; then
    REPO_ROOT="$PREFLIGHT_REPO_ROOT"
elif git_top="$(git rev-parse --show-superproject-working-tree 2>/dev/null)" && [ -n "$git_top" ]; then
    REPO_ROOT="$git_top"
elif git_top="$(git rev-parse --show-toplevel 2>/dev/null)" && [ -n "$git_top" ]; then
    REPO_ROOT="$git_top"
else
    REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"
echo "preflight: repo root = $REPO_ROOT"

FIX_MODE=0
[ "${1:-}" = "--fix" ] && FIX_MODE=1

# Python for scripts that import zw_brain (needs project deps). Override with PYTHON_BIN.
repo_python() {
    if [ -n "${PYTHON_BIN:-}" ]; then
        "$PYTHON_BIN" "$@"
        return $?
    fi
    if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        "$REPO_ROOT/.venv/bin/python" "$@"
        return $?
    fi
    if command -v uv >/dev/null 2>&1 && [ -f "$REPO_ROOT/pyproject.toml" ]; then
        (cd "$REPO_ROOT" && uv run python "$@")
        return $?
    fi
    local py
    py="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)"
    "$py" "$@"
}

contract_regen_hint() {
    if [ -n "${PYTHON_BIN:-}" ]; then
        printf '%s' "$PYTHON_BIN scripts/export_agent_contract.py"
    elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        printf '%s' "$REPO_ROOT/.venv/bin/python scripts/export_agent_contract.py"
    elif command -v uv >/dev/null 2>&1 && [ -f "$REPO_ROOT/pyproject.toml" ]; then
        printf '%s' "uv run python scripts/export_agent_contract.py"
    else
        printf '%s' "python3 scripts/export_agent_contract.py"
    fi
}

errors=0
section() { echo ""; echo "=== $* ==="; }
fail()    { echo "  FAIL: $*"; errors=$((errors + 1)); }
ok()      { echo "  ok: $*"; }
skip()    { echo "  skip: $*"; }

# Standard wrapper for dev-rules upstream check_*.py invocations.
# Usage: run_dev_rules_check <script_basename> <stage_name> <ok_msg> <fail_msg>
# Log file is /tmp/preflight-<script_stem>.log; PYTHON_BIN respected.
run_dev_rules_check() {
    local script="$1" stage="$2" ok_msg="$3" fail_msg="$4"
    local path="dev-rules/scripts/$script"
    local log="/tmp/preflight-$(basename "$script" .py).log"
    section "$stage"
    if [ -f "$path" ]; then
        if "${PYTHON_BIN:-python3}" "$path" > "$log" 2>&1; then
            ok "$ok_msg"
        else
            cat "$log" | sed 's/^/    /'
            fail "$fail_msg"
        fi
    else
        skip "$path not present"
    fi
}

git_sub() {
    local subdir="$1"; shift
    (
        cd "$subdir" || exit 2
        unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_NAMESPACE \
              GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES \
              GIT_COMMON_DIR GIT_PREFIX
        git "$@"
    )
}

section "branch naming (prototype/|feature/|fix/|chore/|docs/|merge/|cursor/|main|master)"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
case "$branch" in
    main|master|prototype/*|feature/*|fix/*|chore/*|docs/*|merge/*|cursor/*|HEAD)
        ok "branch '$branch'"
        ;;
    *)
        fail "branch '$branch' does not match required prefix"
        ;;
esac

section "dev-rules submodule pointer is reachable on remote"
if [ -f .gitmodules ] && grep -q "dev-rules" .gitmodules; then
    sub_sha="$(git submodule status dev-rules | awk '{print $1}' | sed 's/^[+-]//')"
    if git_sub dev-rules cat-file -e "$sub_sha" 2>/dev/null; then
        ok "submodule SHA $sub_sha exists locally in dev-rules"
        if git_sub dev-rules fetch --quiet origin 2>/dev/null && \
           git_sub dev-rules merge-base --is-ancestor "$sub_sha" origin/main 2>/dev/null; then
            ok "submodule SHA is reachable on dev-rules origin/main"
        else
            echo "  warn: cannot verify submodule SHA on remote (offline or not pushed yet)"
        fi
    else
        fail "submodule SHA $sub_sha not found in dev-rules — submodule was not committed first"
    fi
else
    skip "dev-rules submodule not configured"
fi

section "dev-rules sync drift"
if [ -x dev-rules/sync.sh ]; then
    if [ "$FIX_MODE" -eq 1 ]; then
        dev-rules/sync.sh --local && ok "synced from dev-rules mirror"
    else
        if dev-rules/sync.sh --check > /tmp/preflight-sync.log 2>&1; then
            ok "no drift between .cursor/rules/ and dev-rules/rules"
        else
            cat /tmp/preflight-sync.log | sed 's/^/    /'
            fail ".cursor/rules/ has drifted (re-run with --fix)"
        fi
    fi
else
    skip "dev-rules/sync.sh not available"
fi

section "agent contract drift"
if [ -f scripts/export_agent_contract.py ]; then
    if repo_python scripts/export_agent_contract.py --check > /tmp/preflight-contract.log 2>&1; then
        ok "contract docs in sync with code"
    else
        cat /tmp/preflight-contract.log | sed 's/^/    /'
        fail "contract docs have drifted — run $(contract_regen_hint)"
    fi
else
    skip "scripts/export_agent_contract.py not present (enable for contract-bearing projects)"
fi

section "user story / test alignment"
if [ -f .testing/user-stories/verify_quality.py ]; then
    if repo_python .testing/user-stories/verify_quality.py > /tmp/preflight-stories.log 2>&1; then
        ok "stories aligned with tests"
    else
        cat /tmp/preflight-stories.log | sed 's/^/    /'
        fail "story quality / alignment check failed"
    fi
else
    skip ".testing/user-stories/verify_quality.py not present (story workflow not enabled)"
fi

section "docs/approved/ change discipline"
if [ -d docs/approved ]; then
    base="${PREFLIGHT_BASE:-origin/main}"
    if git rev-parse --verify "$base" >/dev/null 2>&1; then
        approved_changed="$(git diff --name-only "$base"...HEAD -- docs/approved/ 2>/dev/null || true)"
        if [ -n "$approved_changed" ]; then
            case "$branch" in
                prototype/*)
                    ok "docs/approved/ modified on prototype branch (allowed)"
                    ;;
                *)
                    echo "  warn: docs/approved/ modified outside prototype/* branch:"
                    echo "$approved_changed" | sed 's/^/    - /'
                    echo "  warn: PR reviewer should confirm this is an intentional approval revision"
                    ;;
            esac
        else
            ok "docs/approved/ unchanged in this branch"
        fi
    else
        skip "no '$base' to diff against"
    fi
else
    skip "docs/approved/ directory not present (high-risk design gate not enabled)"
fi

section "approved-doc invariants (R1-R4 universal + R5 main/master only)"
if [ -d docs/approved ]; then
    if [ -f scripts/check_approved_docs.py ]; then
        if repo_python scripts/check_approved_docs.py 2> /tmp/preflight-approved.log; then
            ok "R1-R4: all approved-doc frontmatter invariants hold"
        else
            cat /tmp/preflight-approved.log | sed 's/^/    /'
            fail "R1-R4: approved-doc invariants violated (see above)"
        fi
    else
        skip "scripts/check_approved_docs.py not present"
    fi

    if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
        pending=$(grep -lE '^approved_by:[[:space:]]*pending[[:space:]]*$' docs/approved/*.md 2>/dev/null || true)
        if [ -n "$pending" ]; then
            echo "$pending" | sed 's/^/    - /'
            fail "R5: files with approved_by: pending must not land on $branch"
        else
            ok "R5: all approved/* files on $branch have a real approver"
        fi
    else
        skip "R5 (approved_by: pending) only enforced on main/master, current=$branch"
    fi
else
    skip "docs/approved/ directory not present (high-risk design gate not enabled)"
fi

section "doc stats vs live values (sync-stats.sh --check)"
if [ -x scripts/sync-stats.sh ]; then
    if [ "$FIX_MODE" -eq 1 ]; then
        scripts/sync-stats.sh --update | sed 's/^/    /'
        ok "stat blocks updated to live values"
    else
        if scripts/sync-stats.sh --check > /tmp/preflight-stats.log 2>&1; then
            ok "all stat blocks match live values"
        else
            cat /tmp/preflight-stats.log | sed 's/^/    /'
            fail "doc stats have drifted (re-run with --fix or 'scripts/sync-stats.sh --update')"
        fi
    fi
else
    skip "scripts/sync-stats.sh not available"
fi

run_dev_rules_check check_contract_deletion_notice.py \
    "contract deletion notice" \
    "contract deletion: no public-contract paths removed (or notice token present)" \
    "contract deletion requires explicit notice token in commit message"

run_dev_rules_check check_web_surface_alignment.py \
    "web surface alignment" \
    "web surface: backend changes paired with web review (or web-only)" \
    "backend changes need web-surface review note (or no-web-impact declaration)"

run_dev_rules_check check_high_risk_anchor.py \
    "high-risk approval anchor" \
    "high-risk anchor: no migrations/schema changes (or approved-doc anchor present)" \
    "high-risk path change requires anchor in docs/approved/* (token: high-risk-anchor)"

run_dev_rules_check check_workflow_yaml.py \
    "workflow yaml hygiene" \
    "workflow yaml clean (no env.* in job-level if, claude -p has --allowedTools)" \
    ".github/workflows/*.yml has hard-failure patterns (see above)"

run_dev_rules_check check_existence_only_tests.py \
    "no existence-only tests" \
    "no existence-only tests (per test-philosophy.mdc)" \
    "test(s) only assert file existence — replace with behavior assertions"

run_dev_rules_check check_deleted_file_refs.py \
    "deleted files not still referenced (config/frontmatter)" \
    "no dangling references to deleted files" \
    "deleted file(s) still referenced in build config or doc frontmatter — fix reference or restore file"

section "cloud-agent env consistency (tools + secrets, both local and cloud)"
if [ -f .cursor/cloud-agent.env ] && [ -x dev-rules/templates/cloud-agent-bootstrap.sh ]; then
    if [ -z "${CLOUD_AGENT_FORCE_CHECK:-}" ] && \
       { [ "${CI:-}" = "true" ] || [ -n "${GITHUB_ACTIONS:-}" ] || [ -n "${GITLAB_CI:-}" ] || [ -n "${BUILDKITE:-}" ] || [ -n "${CIRCLECI:-}" ]; }; then
        skip "generic CI runner detected (CI / GITHUB_ACTIONS / GITLAB_CI / …) — cloud-agent contract is for cloud-agent + local dev sessions; set CLOUD_AGENT_FORCE_CHECK=1 to override"
    elif CLOUD_AGENT_REPO_ROOT="$REPO_ROOT" \
         dev-rules/templates/cloud-agent-bootstrap.sh --check > /tmp/preflight-cloud-agent.log 2>&1; then
        ok "cloud-agent env consistent (tools + required secrets present)"
    else
        cat /tmp/preflight-cloud-agent.log | sed 's/^/    /'
        fail "cloud-agent env inconsistent (missing required tool or secret — see above)"
    fi
else
    skip ".cursor/cloud-agent.env not present (cloud-agent contract not declared for this project)"
fi

echo ""
if [ $errors -eq 0 ]; then
    echo "=== preflight: PASS ==="
    exit 0
else
    echo "=== preflight: FAIL ($errors check(s) failed) ==="
    exit 1
fi
