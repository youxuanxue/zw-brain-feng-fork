#!/usr/bin/env bash
#
# zw-brain: vendored sync-stats (design-contract stat blocks in prose).
# Registry: scripts/.stats.json
#
# 用法：
#   ./scripts/sync-stats.sh --update | --check | --list

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATS_FILE="$SCRIPT_DIR/.stats.json"

if [ -n "${SYNC_STATS_REPO:-}" ] && [ -d "$SYNC_STATS_REPO" ]; then
    REPO_ROOT="$SYNC_STATS_REPO"
elif git_top="$(git rev-parse --show-superproject-working-tree 2>/dev/null)" && [ -n "$git_top" ]; then
    REPO_ROOT="$git_top"
elif git_top="$(git rev-parse --show-toplevel 2>/dev/null)" && [ -n "$git_top" ]; then
    REPO_ROOT="$git_top"
else
    REPO_ROOT="$(pwd)"
fi

if [ ! -f "$STATS_FILE" ]; then
    echo "FAIL: $STATS_FILE not found"
    exit 2
fi

MODE="${1:-}"
case "$MODE" in
    --update|--check|--list) ;;
    *) echo "Usage: $0 --update | --check | --list"; exit 2 ;;
esac

extract_stats() {
    python3 -c "
import json, sys
with open('$STATS_FILE') as f:
    data = json.load(f)
for name, spec in data.get('stats', {}).items():
    print(f\"{name}\t{spec['compute']}\")
" 2>/dev/null || {
        echo "FAIL: cannot parse $STATS_FILE (need python3)" >&2
        exit 2
    }
}

compute_stat() {
    local cmd="$1"
    (cd "$REPO_ROOT" && bash -c "$cmd" 2>/dev/null | tr -d '\n')
}

if [ "$MODE" = "--list" ]; then
    echo "=== sync-stats: live values (repo root: $REPO_ROOT) ==="
    while IFS=$'\t' read -r name cmd; do
        val="$(compute_stat "$cmd")"
        printf "  %-28s = %s\n" "$name" "$val"
    done < <(extract_stats)
    exit 0
fi

find_doc_files() {
    find "$REPO_ROOT" \
        \( -name .git -o -name .claude -o -name node_modules -o -name backups -o -name old -o -name '.stats.json' -o -name dev-rules \) -prune \
        -o \( -name '*.md' -o -name '*.mdc' \) -print 2>/dev/null
}

update_file() {
    local file="$1" name="$2" newval="$3"
    perl -i -pe "s|(<!-- stat:\Q$name\E -->)[^<]*?(<!-- /stat -->)|\${1}\Q$newval\E\${2}|g" "$file"
}

check_file() {
    local file="$1" name="$2" expected="$3"
    local drift=0
    while IFS=: read -r lineno content; do
        actual=$(echo "$content" | sed -nE "s|.*<!-- stat:$name -->([^<]*)<!-- /stat -->.*|\1|p")
        if [ -n "$actual" ] && [ "$actual" != "$expected" ]; then
            echo "  DRIFT: $file:$lineno stat=$name doc='$actual' live='$expected'"
            drift=1
        fi
    done < <(grep -nE "<!-- stat:$name -->[^<]*<!-- /stat -->" "$file" 2>/dev/null)
    return $drift
}

total_drift=0
total_updated=0
declare -a CHANGED_FILES

while IFS=$'\t' read -r name cmd; do
    expected="$(compute_stat "$cmd")"
    if [ -z "$expected" ]; then
        echo "  WARN: stat '$name' compute returned empty (cmd: $cmd)"
        continue
    fi

    while IFS= read -r f; do
        [ -f "$f" ] || continue
        grep -qE "<!-- stat:$name -->" "$f" 2>/dev/null || continue

        if [ "$MODE" = "--check" ]; then
            if ! check_file "$f" "$name" "$expected"; then
                total_drift=$((total_drift + 1))
            fi
        else
            update_file "$f" "$name" "$expected"
            if ! git diff --quiet -- "$f" 2>/dev/null; then
                rel="${f#$REPO_ROOT/}"
                CHANGED_FILES+=("$rel:$name")
                total_updated=$((total_updated + 1))
            fi
        fi
    # 上游 dev-rules#73 移植：单趟 grep 预过滤——先把候选窄化到真含该 stat 标记的文件，
    # 不再对全量 md/mdc 逐文件 grep -q（本脚本每次 commit 经 preflight 跑 --check，stat 数 × 文档数放大）。
    # 循环体内保留逐文件 re-assert（窄化列表上开销可忽略，防预过滤将来变化时循环体失守）。
    done < <(find_doc_files | tr '\n' '\0' | xargs -0 grep -lE "<!-- stat:$name -->" /dev/null 2>/dev/null)
done < <(extract_stats)

if [ "$MODE" = "--check" ]; then
    if [ "$total_drift" -eq 0 ]; then
        echo "sync-stats: ok (no drift in repo root: $REPO_ROOT)"
        exit 0
    else
        echo ""
        echo "sync-stats: $total_drift drift instance(s). Run: scripts/sync-stats.sh --update"
        exit 1
    fi
else
    if [ "$total_updated" -eq 0 ]; then
        echo "sync-stats: ok (all $((${#CHANGED_FILES[@]})) blocks already in sync)"
    else
        echo "sync-stats: updated $total_updated stat block(s):"
        for entry in "${CHANGED_FILES[@]}"; do
            echo "  - $entry"
        done
    fi
fi
