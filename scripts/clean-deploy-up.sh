#!/usr/bin/env bash
# clean-deploy-up.sh — 一键「只导入干净数据」的本地演示种子（--only-clean）。
#
# 与 seed-deploy-demo-data.sh 的区别：业务记录（目录/资源/申请）只收符合 zw-brain 标准的
# 干净数据，不达标的（测试/未命名标题、缺机构、脏用途、悬空引用…）在导入时跳过并记账
# （stats.skip "<table>.unclean:<reason>"，可审计、非静默）。治理基线（机构/区划/字典/actor）
# 仍完整导入（demo 需要完整机构树与字典下拉）。承 D11：不是造假数据，是只收够格的真实数据。
#
# 后端 = PostgreSQL。目标库 = resolved ZW_BRAIN_DATABASE_URL（默认本机 dev PG；docker compose
# 把容器库发布到宿主 5433，故默认连 127.0.0.1:5433）。用 HOST venv 跑导入（working-tree 代码，
# 含 --only-clean），与 customer_acceptance_up.sh / trial-up.sh 同范式。
#
# 用法：
#   docker compose -p zw-brain-deploy-clean up -d postgres   # 起库（或整栈）
#   bash scripts/clean-deploy-up.sh                          # 干净种子（reset + --only-clean import + fixtures）
#
# 全量（含脏数据、真实规模）走 scripts/seed-deploy-demo-data.sh --reset；二者并存，按演示目的选。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ZW_BRAIN_PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
DUMPS_DIR="${ZW_BRAIN_LEGACY_DUMPS_DIR:-$REPO_ROOT/old/10示例数据}"
export ZW_BRAIN_DATABASE_URL="${ZW_BRAIN_DATABASE_URL:-postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5433/zw_brain}"
export ZW_BRAIN_LEGACY_DUMPS_DIR="$DUMPS_DIR"

# 治理基线须最先（建 actor/dict/org/region 投影，下游 catalog/exchange 依赖）。
# --only-clean 只影响业务 mapper（catalog_metadata / exchange）；dsp_bsp / dsp_pipelines 治理不过滤。
# dsp_pipelines 建 datasource_endpoint_projection（#360 已合 main；本地干净种子与 docker demo 对齐）。
SCHEMAS="dsp_bsp dsp_catalog dsp_metaresource dsp_require dsp_handling dsp_example dsp_pipelines"

step() { printf '\n[clean-deploy] === %s ===\n' "$1"; }
fail() { printf '[clean-deploy] FAIL: %s\n' "$1" >&2; exit 1; }

[[ -x "$PYTHON" ]] || fail "missing venv python at $PYTHON（python3 -m venv .venv && .venv/bin/pip install -e '.[postgres]'）"
[[ -d "$DUMPS_DIR" ]] || fail "missing legacy dumps dir: $DUMPS_DIR"

step "reset schema on $(printf '%s' "$ZW_BRAIN_DATABASE_URL" | sed -E 's#//[^@]*@#//<cred>@#')"
ZW_BRAIN_ALLOW_SCHEMA_RESET=1 "$PYTHON" - <<'PY' || fail "schema reset failed（确认 PG 已起且 ZW_BRAIN_DATABASE_URL 可连）"
from zw_brain.shared.db import reset_engine_cache
from zw_brain.shared.migrate import reset_and_upgrade
reset_engine_cache()
reset_and_upgrade()
print("[clean-deploy] schema rebuilt")
PY

for schema in $SCHEMAS; do
  step "import $schema --only-clean"
  "$PYTHON" "$REPO_ROOT/scripts/import_legacy_dumps.py" import "$schema" --only-clean || fail "import $schema failed"
done

step "fixtures: national-escalate + demo J1 credential"
"$PYTHON" "$REPO_ROOT/scripts/seed_national_escalate_fixture.py" || echo "[clean-deploy] WARN: national fixture skipped (non-fatal)"
"$PYTHON" "$REPO_ROOT/scripts/customer_demo_j1.py" >/dev/null 2>&1 && echo "[clean-deploy] demo J1 credential seeded" || echo "[clean-deploy] WARN: demo J1 skipped (clean DB 可能无 medical-aid 目录，非致命)"

step "counts (clean vs 全量对比可跑 seed-deploy-demo-data.sh 看差值)"
"$PYTHON" - <<'PY'
from sqlalchemy import create_engine, text
from zw_brain.shared.db import get_database_url
eng = create_engine(get_database_url())
with eng.connect() as con:
    for t in ("org_projection", "dict_projection", "actor_projection", "catalog_entry", "resource_asset", "application_record", "approval_case", "delivery_task"):
        n = con.execute(text(f"select count(*) from {t}")).scalar_one()
        print(f"[clean-deploy] {t}={n}")
PY

printf '\n[clean-deploy] 干净种子完成。全量（含脏数据/真实规模）：bash scripts/seed-deploy-demo-data.sh --reset\n'
