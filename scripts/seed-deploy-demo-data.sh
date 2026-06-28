#!/usr/bin/env bash
# Seed the Docker compose demo stack with real legacy data.
#
# This intentionally runs the importer inside the compose network and targets
# postgresql://...@postgres:5432 so it cannot accidentally write to a host-local
# PostgreSQL on 127.0.0.1:5432.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-zw-brain-deploy-clean}"
NETWORK_NAME="${ZW_BRAIN_COMPOSE_NETWORK:-${COMPOSE_PROJECT_NAME}_zw-brain-net}"
IMAGE="${ZW_BRAIN_IMAGE:-zw-brain:latest}"
DUMPS_DIR="${ZW_BRAIN_LEGACY_DUMPS_DIR:-$REPO_ROOT/../zw-brain/old/10示例数据}"
REPORT_DIR_HOST="${ZW_BRAIN_DEMO_SEED_REPORT_DIR:-$REPO_ROOT/.data/deploy-demo-seed}"
case "$REPORT_DIR_HOST" in
  "$REPO_ROOT"/*) REPORT_DIR_CONTAINER="/src/${REPORT_DIR_HOST#"$REPO_ROOT"/}" ;;
  *) echo "[demo-seed] ZW_BRAIN_DEMO_SEED_REPORT_DIR must live under repo root: $REPORT_DIR_HOST" >&2; exit 1 ;;
esac
DB_URL="${ZW_BRAIN_DEMO_DATABASE_URL:-postgresql+psycopg://zw_brain:zw_brain@postgres:5432/zw_brain}"
RESET=0

usage() {
  cat <<'USAGE'
seed-deploy-demo-data.sh [--reset]

Seeds a running Docker compose stack with real legacy demo data.

Environment:
  COMPOSE_PROJECT_NAME            compose project (default: zw-brain-deploy-clean)
  ZW_BRAIN_LEGACY_DUMPS_DIR       real dump dir (default: ../zw-brain/old/10示例数据)
  ZW_BRAIN_IMAGE                  image used for the importer (default: zw-brain:latest)

Options:
  --reset                         drop/rebuild the target PostgreSQL schema first
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "[demo-seed] unknown arg: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -d "$DUMPS_DIR" ]] || {
  echo "[demo-seed] missing legacy dumps dir: $DUMPS_DIR" >&2
  echo "[demo-seed] set ZW_BRAIN_LEGACY_DUMPS_DIR to old/10示例数据" >&2
  exit 1
}

mkdir -p "$REPORT_DIR_HOST"

docker network inspect "$NETWORK_NAME" >/dev/null

docker run --rm \
  --network "$NETWORK_NAME" \
  -v "$REPO_ROOT:/src" \
  -v "$DUMPS_DIR:/legacy-dumps:ro" \
  -w /src \
  --entrypoint /bin/sh \
  "$IMAGE" \
  -c '
set -eu
export PYTHONPATH=/src
export ZW_BRAIN_DATABASE_URL="'"$DB_URL"'"
export ZW_BRAIN_LEGACY_DUMPS_DIR=/legacy-dumps
mkdir -p "'"$REPORT_DIR_CONTAINER"'"

if [ "'"$RESET"'" = "1" ]; then
  ZW_BRAIN_ALLOW_SCHEMA_RESET=1 python - <<'"'"'PY'"'"'
from zw_brain.shared.db import get_database_url, reset_engine_cache
from zw_brain.shared.migrate import reset_and_upgrade

reset_engine_cache()
reset_and_upgrade()
print(f"[demo-seed] schema rebuilt on {get_database_url()}")
PY
fi

# dsp_bsp（治理基线）必须最先导入：它经 tests/fixtures/m0-sd-default/iaf-binding-manifest.json
# 建 actor_projection（用户）+ actor_org_role_binding（角色绑定）+ 完整 org/region 投影，
# 下游 catalog/exchange 适配器解析机构/区划时依赖它（口径同 trial-up.sh DEFAULT_SCHEMAS /
# customer_acceptance_up.sh REQUIRED_SCHEMAS）。此前漏 dsp_bsp → actor_projection=0、
# 身份治理用户列表空、权限/部门隔离类 e2e 全失败（仅靠脚本末尾手工 upsert 6 org 兜底机构）。
# 补 dsp_pipelines：经 DatasourceEndpointMapper 建 datasource_endpoint_projection——此前漏导致
# #/provider/datasources 空。仅补这一项（用户实测缺口）；权威全集 migration_batch.PROFILE_SCHEMAS
# ["customer-core-v1"] 另含 dsp_connect/dsp_service/dsp_monitor/dsp_perform，但 demo 不导入：
# dsp_service/connect 会把 catalog 从 ~226 膨胀到 ~1200（API 服务/连接条目涌入发现页、拖慢筛选）。
# 生产迁移（zw-brain-migrate-legacy / run_acceptance_migration）走全 11 schema，不受此 demo 取舍影响。
for schema in dsp_bsp dsp_catalog dsp_metaresource dsp_require dsp_handling dsp_example dsp_pipelines; do
  echo "[demo-seed] import $schema"
  python scripts/import_legacy_dumps.py import "$schema" --json > "'"$REPORT_DIR_CONTAINER"'/import-${schema}.json"
done

# e2e/demo fixtures（容器内 in-network，写 postgres:5432，不依赖 host 端口——避免 host-venv 连
# 5432/5433 撞 Homebrew pg）：国家通道待转报样例 + demo J1 凭据，供 national_channel / 凭据三语样例
# e2e 与演示用。非致命：失败只告警，不阻断种子。
python scripts/seed_national_escalate_fixture.py || echo "[demo-seed] WARN: national fixture 跳过（非致命）"
python scripts/customer_demo_j1.py >/dev/null 2>&1 && echo "[demo-seed] demo J1 凭据已种子" || echo "[demo-seed] WARN: demo J1 跳过（非致命）"

python - <<'"'"'PY'"'"'
from sqlalchemy import create_engine, text
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared.db import get_database_url

repo = GovernanceProjectionRepository()
orgs = [
    ("11370000MB284651XL", "省大数据局", "370000000000"),
    ("11360000014501340W", "江西省教育厅", "360000000000"),
    ("36010000876", "南昌市教育局", "360100000000"),
    ("11370000004504927A", "省公安厅", "370000000000"),
    ("113700000045022274", "省人民政府办公厅", "370000000000"),
    ("00510101", "市行政审批局", "005101"),
]
for code, name, region in orgs:
    repo.upsert_org(
        {
            "org_code": code,
            "org_name": name,
            "region_code": region,
            "status": "active",
            "source_ref": "deploy-demo:legacy-demo-org-seed",
            "profile_json": {"seed_reason": "legacy demo visible scope", "org_name": name},
        }
    )

engine = create_engine(get_database_url())
tables = [
    "org_projection",
    "catalog_entry",
    "resource_asset",
    "application_record",
    "approval_case",
    "delivery_task",
]
with engine.connect() as con:
    for table in tables:
        count = con.execute(text(f"select count(*) from {table}")).scalar_one()
        print(f"[demo-seed] {table}={count}")
PY
'

echo "[demo-seed] reports: $REPORT_DIR_HOST"
