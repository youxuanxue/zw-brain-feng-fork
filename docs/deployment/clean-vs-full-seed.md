# 种子数据：全量 vs `--only-clean`（干净）

历史 dump（`old/10示例数据/*`）是真实政务数据，含大量脏业务记录（测试/未命名标题、纯数字/「测试」用途、缺机构、悬空引用…）。两种种子模式**都全量读取这份 dump**，唯一区别是导入时是否过滤不达标的业务记录。

| | 全量（默认） | `--only-clean`（干净） |
|---|---|---|
| 业务记录（目录/资源/申请/审批/交付） | 原样全收（含脏数据、真实规模） | 只收符合 zw-brain 标准的；不达标的跳过并记 `stats.skip("<table>.unclean:<reason>")`（可审计、非静默）|
| 治理基线（机构/区划/字典/用户） | 全收 | **同样全收**（demo 需完整机构树与字典下拉，不过滤）|
| 用途 | 压测 / 真实规模回归 / 看真实脏数据治理 | 演示 / 试用：前台观感干净，无测试名目录、无脏用途 |

> 承 D11：`--only-clean` 不是造假数据，是**只收够格的真实数据**。

## 一、本地部署（host venv，连 compose 库）

```bash
docker compose -p zw-brain-deploy-clean up -d postgres   # 起库（或整栈）

# 干净种子（reset + 全 schema --only-clean 导入 + national/J1 fixture + 打印计数）
bash scripts/clean-deploy-up.sh

# 全量种子（含脏数据 / 真实规模）
COMPOSE_PROJECT_NAME=zw-brain-deploy-clean bash scripts/seed-deploy-demo-data.sh --reset
```

宿主连接：默认 `ZW_BRAIN_DATABASE_URL=postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5433/zw_brain`（compose 把容器库发布到宿主 5433；若本机 5432 空闲可自行调整 compose 端口）。

## 二、Docker 部署（容器内导入，写 `postgres:5432` 服务名）

```bash
docker compose -p zw-brain-deploy-clean up -d            # 起三件套

# 干净种子
COMPOSE_PROJECT_NAME=zw-brain-deploy-clean bash scripts/seed-deploy-demo-data.sh --reset --only-clean

# 全量种子
COMPOSE_PROJECT_NAME=zw-brain-deploy-clean bash scripts/seed-deploy-demo-data.sh --reset
```

> `--only-clean` 在容器内由 `zw-brain:latest` 镜像的导入器执行，故镜像须含本特性（合并后重建镜像即可）。

## 三、生产数据迁移（`zw-brain-migrate-legacy`，真实 IAF + 真实 dump）

> 上面一、二是 **demo/试用种子**（脱敏样例 `old/10示例数据`）。**生产**首次上线导入真实脱敏 dump 走独立的一次性迁移命令 `zw-brain-migrate-legacy`（`run_acceptance_migration`，profile `customer-core-v1` 全 11 schema），与 demo 种子脚本无关。该命令同样支持 `--only-clean`：

```bash
docker run --rm \
  -v /path/to/desensitized-legacy-dumps:/legacy-dumps:ro \
  -v /opt/zw-brain/reports:/reports \
  -e ZW_BRAIN_DATABASE_URL=postgresql+psycopg://zw_brain:***@db.intranet:5432/zw_brain \
  zw-brain:1.0.0 \
  zw-brain-migrate-legacy \
    --dumps-dir /legacy-dumps --profile customer-core-v1 \
    --strict --acceptance --only-clean \
    --report /reports/legacy-migration-clean-report.json
```

`only_clean` 经 `MigrationOptions` → `run_acceptance_migration` 的每个 stage → `LegacyImportRunner` → 各 mapper 贯穿；报告记录 `only_clean: true`。复跑请确认数据可丢弃后加 `--reset-db`。细节见 `docs/deployment/docker-image-deployment.md` §6。

## 四、数据差异（同一份 dump 全量读取，唯一变量 = `--only-clean`）

| 数据 | 来源表 | 全量 | `--only-clean` | 差值 |
|---|---|---:|---:|---:|
| 目录 catalog_entry | data_catalog + data_basic_elem_catalog | 226 | 185 | **−41** |
| 资源 resource_asset | data_resource | 144 | 131 | **−13** |
| 申请 application_record | data_apply | 226 | 174 | **−52** |
| 审批 approval_case | data_apply_dept_approve | 230 | 188 | **−42** |
| 交付 delivery_task | data_apply_authrization | 19 | 1 | **−18** |
| 机构 org_projection | dsp_bsp | 18750 | 18750 | 0 |
| 区划 region_projection | dsp_bsp | 16731 | 16731 | 0 |
| 字典 dict_projection | dsp_bsp | 802 | 802 | 0 |
| 用户 actor_projection | dsp_bsp | 710 | 710 | 0 |

过滤记账（行级，可审计）：`application.dirty_use_item`、`catalog.bad_name`、`resource.bad_name`、`application.bad_resource_name`，以及联动跳过 `application.parent_filtered`（被过滤申请的 course/dept_approve/authrization 子记录）。干净库测试名目录残留 = 0。

> 数字随 dump 版本浮动；以实际 `stats.skip` 记账为准。

## 五、判据与联动

- **判据单源**：`zw_brain/adapters/legacy/clean_filter.py: is_clean_record(kind, record)`。「什么算干净」是业务标准（GATE），可在此调整：catalog=名称干净+有机构；resource=名称干净；application=有资源引用+资源名干净+机构非占位+用途非脏值。
- **联动过滤**：申请被过滤时，其审批/交付子记录（`data_apply_course` / `data_apply_dept_approve` / `data_apply_authrization`）一并跳过（`application.parent_filtered`），避免「孤儿审批/交付」。
- **治理基线不过滤**：`dsp_bsp`（机构/区划/字典/actor）由独立 mapper 导入，不受 `--only-clean` 影响。
