# read-path full-scan 豁免清单

本清单由 `scripts/generate_full_scan_exemptions.py` 自动生成；不要手编辑。

**Review 周期**：每月一次（与 `docs/preflight-debt.md` debt review 同步——
详见架构基线 §9.7.5）。每月把存活豁免逐条复核，问 3 个问题：

1. trigger 条件是否已被现实触及（如多租户接入 / J1 量级进入万级）？
2. PR 范围允许在本月把它修掉吗？
3. 否则保留并把当月复核日期写进 reason 注释。

**机械守卫**：段 32 `check_read_path_full_scan.py` 对**新增**全表扫一律拦下，
必须显式加 `# full-scan-ok: <≥7 字符理由>` 才放行；段 32b 本脚本以 `--check`
模式校验本清单与代码同步。

当前豁免总数：**12** 条，分布在 8 个文件。

---

## `zw_brain/command/handlers/j2/metadata.py`

### `zw_brain/command/handlers/j2/metadata.py:42`

**Reason**: summary_json.source 是 JSON 列上的 reverse-source 过滤；

```python
        ).scalars().all()
        # full-scan-ok: summary_json.source 是 JSON 列上的 reverse-source 过滤；
        # 等同于 supply_demand.list_demands 的 JSON 维度场景；当前 catalog ≤ 1.2 万行，
```

## `zw_brain/domain/repositories/application.py`

### `zw_brain/domain/repositories/application.py:39`

**Reason**: J1 申请记录全量被多个 handler 共享（governance / dispute /

```python
    def list_records(self, *, tenant_id: str = "sd-default") -> list[ApplicationRecord]:
        # full-scan-ok: J1 申请记录全量被多个 handler 共享（governance / dispute /
        # approval listing），二次 in-memory filter 走 application_code lookup；
```

## `zw_brain/domain/repositories/approval.py`

### `zw_brain/domain/repositories/approval.py:18`

**Reason**: handler 侧多个 next(... for ... if application_code == X) 二次过滤；

```python
    def list_cases(self, *, tenant_id: str = "sd-default") -> list[ApprovalCaseRecord]:
        # full-scan-ok: handler 侧多个 next(... for ... if application_code == X) 二次过滤；
        # ApprovalCase 行数 ≈ Application 行数，trigger 与 application.list_records 同步。
```

## `zw_brain/domain/repositories/catalog.py`

### `zw_brain/domain/repositories/catalog.py:261`

**Reason**: builder 基座仅 tenant；调用方须传 lifecycle/owner/prefix/limit（PR #113 修复路径）

```python
            statement = statement.where(CatalogEntryRecord.catalog_code != exclude_catalog_code)
        # full-scan-ok: builder 基座仅 tenant；调用方须传 lifecycle/owner/prefix/limit（PR #113 修复路径）
        # trigger: list_entries 默认全 None 且无 limit 时等同 #113 全扫 — 见 preflight-debt §2026-05-26
```

### `zw_brain/domain/repositories/catalog.py:491`

**Reason**: catalog_code 可选；None 时 tenant-only 全量 item；当前单租户 <1k

```python
    def list_items(self, catalog_code: str | None = None, *, tenant_id: str = "sd-default") -> list[CatalogItemRecord]:
        # full-scan-ok: catalog_code 可选；None 时 tenant-only 全量 item；当前单租户 <1k
        # trigger: catalog 万级或多租户时改必填 catalog_code 或 paged list_items
```

### `zw_brain/domain/repositories/catalog.py:501`

**Reason**: legacy verification 一次性 count/set-membership 用途；method 名带 _all

```python
    def list_model_fields_all(self, *, tenant_id: str = "sd-default") -> list[CatalogModelFieldRecord]:
        # full-scan-ok: legacy verification 一次性 count/set-membership 用途；method 名带 _all
        # 显式声明全量；当前单租户 sd-default 下行数 ≤ 数千；trigger: 多租户启用后改 join filter。
```

## `zw_brain/domain/repositories/delivery.py`

### `zw_brain/domain/repositories/delivery.py:26`

**Reason**: J1 投递任务上限 = 已申请通过的资源数；当前单租户下 <1k；

```python
    def list_tasks(self, *, tenant_id: str = "sd-default") -> list[DeliveryTaskRecord]:
        # full-scan-ok: J1 投递任务上限 = 已申请通过的资源数；当前单租户下 <1k；
        # trigger: J1 申请量进入万级或第二个租户接入时改 paged + 状态过滤。
```

### `zw_brain/domain/repositories/delivery.py:81`

**Reason**: delivery_code/attempt_code 可选；双 None 时 tenant-only 全量 attempt

```python
    def list_attempts(self, delivery_code: str | None = None, attempt_code: str | None = None, *, delivery_codes: list[str] | None = None, tenant_id: str = "sd-default") -> list[DeliveryAttemptRecord]:
        # full-scan-ok: delivery_code/attempt_code 可选；双 None 时 tenant-only 全量 attempt
        # trigger: J1 投递量万级或多租户时改 paged + 必填 delivery_code
```

## `zw_brain/domain/repositories/objection.py`

### `zw_brain/domain/repositories/objection.py:50`

**Reason**: status 可选；None 时 tenant-only 全量 objection case；当前单租户 <1k

```python
    ) -> list[ObjectionCaseRecord]:
        # full-scan-ok: status 可选；None 时 tenant-only 全量 objection case；当前单租户 <1k
        # trigger: 异议工单万级或多租户时改 paged + 默认 status 过滤
```

## `zw_brain/domain/repositories/resource_api.py`

### `zw_brain/domain/repositories/resource_api.py:29`

**Reason**: lifecycle_status 可选；None 时 tenant-only 全量 resource asset

```python
    ) -> list[ResourceAssetRecord]:
        # full-scan-ok: lifecycle_status 可选；None 时 tenant-only 全量 resource asset
        # trigger: 资源量万级或多租户时改 paged + 默认 lifecycle 过滤
```

### `zw_brain/domain/repositories/resource_api.py:251`

**Reason**: resource_code 可选；None 时 tenant-only 全量 channel binding

```python
    def list_bindings(self, resource_code: str | None = None, *, resource_codes: list[str] | None = None, tenant_id: str = "sd-default") -> list[ResourceChannelBindingRecord]:
        # full-scan-ok: resource_code 可选；None 时 tenant-only 全量 channel binding
        # trigger: 绑定量万级或多租户时改 paged + 必填 resource_code
```

## `zw_brain/domain/repositories/supply_demand.py`

### `zw_brain/domain/repositories/supply_demand.py:148`

**Reason**: kind/response_status 存 payload_json JSON 列，需 SQL JSON 算子

```python
        with SessionLocal() as session:
            # full-scan-ok: kind/response_status 存 payload_json JSON 列，需 SQL JSON 算子
            # （SQLite vs PG 分支）才能下推；当前演示规模 <500 行，先内存过滤。
```

