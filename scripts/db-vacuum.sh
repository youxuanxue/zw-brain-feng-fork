#!/usr/bin/env bash
# db-vacuum.sh — 周期清理 zw-brain canonical sqlite DB 的膨胀
#
# 用途：
#   sqlite 的 default journal_mode=WAL + 大量 audit_event / anchor_outbox
#   写入会让物理文件远大于实际行数。VACUUM 重建 b-tree、释放 free pages。
#
# 默认目标：$ZW_BRAIN_DB_PATH 或 $REPO/.data/zw_brain.db
# 历史残留：可顺手清 .data/customer_acceptance.db / *.pre-m0-* / legacy-dryrun.db
#
# 建议触发时机：
#   - 每周 cron 一次（k8s CronJob / launchd / systemd timer）
#   - 客户机房 deploy 前
#   - preflight 段 18 触发 db-bloat 报警时
#
# 用法：
#   bash scripts/db-vacuum.sh                                  # vacuum 默认 DB（写动作）
#   bash scripts/db-vacuum.sh --include-legacy                 # 同时清历史残留 → 默认 dry-run
#   bash scripts/db-vacuum.sh --include-legacy --apply         # 真正删历史残留
#   bash scripts/db-vacuum.sh --dry-run                        # vacuum 也只看不做
#   ZW_BRAIN_DB_PATH=/path/to/db bash scripts/db-vacuum.sh
#
# 安全设计：
#   - --include-legacy 涉及 rm `*.pre-m0-*` / customer_acceptance.db-wal 等历史数据，
#     默认 **dry-run**，必须加 --apply 才会真删，避免运维手滑丢备份。
#   - VACUUM 期间持有 EXCLUSIVE lock。必先停 REST（脚本内已检测 lsof）。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${ZW_BRAIN_DB_PATH:-$REPO_ROOT/.data/zw_brain.db}"
INCLUDE_LEGACY=0
DRY_RUN=0
APPLY=0

for arg in "$@"; do
  case "$arg" in
    --include-legacy) INCLUDE_LEGACY=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --apply) APPLY=1 ;;
    -h|--help)
      sed -n '/^#/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "FATAL: unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# --include-legacy 必须显式 --apply 才会真删；其余仅 vacuum 用户传 --dry-run 决定
if (( INCLUDE_LEGACY )) && ! (( APPLY )); then
  DRY_RUN=1
  echo "[db-vacuum] note: --include-legacy 默认进入 dry-run（避免误删历史 DB / 备份）；"
  echo "[db-vacuum] note: 确认无误后追加 --apply 真正执行"
fi

step() { printf '\n[db-vacuum] === %s ===\n' "$1"; }
ok() { printf '[db-vacuum] ok: %s\n' "$1"; }
fail() {
  printf '[db-vacuum] FAIL: %s\n' "$1" >&2
  if [[ -n "${2:-}" ]]; then printf '[db-vacuum] next-step: %s\n' "$2" >&2; fi
  exit 1
}

require_db_idle() {
  local db="$1"
  if command -v lsof >/dev/null && lsof -- "$db" >/dev/null 2>&1; then
    fail "DB $db 正在被持有：先停 REST / dashboard 再来" \
      "lsof '$db'  # 看是哪个进程；通常是 zw_brain.entry.rest"
  fi
}

vacuum_one() {
  local db="$1"
  [[ -f "$db" ]] || { ok "$db 不存在，skip"; return 0; }
  local before
  before=$(stat -f%z "$db" 2>/dev/null || stat -c%s "$db")
  step "vacuum $db (before=${before} bytes)"
  require_db_idle "$db"
  if (( DRY_RUN )); then
    ok "dry-run: 跳过 VACUUM；预计释放约 80% 空间（典型场景）"
    return 0
  fi
  sqlite3 "$db" "VACUUM;" || fail "VACUUM $db 失败" "DB 可能损坏，先 .data backup 再人工 sqlite3 修复"
  local after
  after=$(stat -f%z "$db" 2>/dev/null || stat -c%s "$db")
  local saved=$(( before - after ))
  ok "after=${after} bytes，释放 ${saved} bytes"
}

# 1. canonical DB
vacuum_one "$DB_PATH"

# 2. legacy 残留（可选）
if (( INCLUDE_LEGACY )); then
  step "扫描 .data/ 历史残留 DB"
  shopt -s nullglob
  for stale in \
    "$REPO_ROOT/.data/customer_acceptance.db" \
    "$REPO_ROOT/.data/customer_acceptance.db-wal" \
    "$REPO_ROOT/.data/customer_acceptance.db-shm" \
    "$REPO_ROOT/.data/legacy-dryrun.db" \
    "$REPO_ROOT/.data/zw_brain.db.pre-m0-"*
  do
    [[ -e "$stale" ]] || continue
    if [[ "$stale" == *.db ]]; then
      vacuum_one "$stale"
    else
      step "rm $stale"
      if (( DRY_RUN )); then ok "dry-run: skip rm"; else rm -f "$stale" && ok "removed"; fi
    fi
  done
fi

step "done"
ok "canonical DB: $DB_PATH"
ok "完成 vacuum；建议每周跑一次"
