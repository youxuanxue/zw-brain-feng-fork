# ADR — audit_class 三级正规化（F1 / D4 收口）

- 提案人：F1 worker
- 日期：2026-05-24
- 状态：accepted（随 F1 落地）
- 关联：docs/approved/zw-brain-architecture.md §6.4 + D4；scripts/check_audit_must_block.py
- 取消候选：无（如 Wave 2 三引擎要求新增「config-change」语义需要第 4 级，再开新 ADR）

## 背景

设计基线 §6.4 + D4 规定审计总线**只有 3 级**：

```text
write-critical / write-normal / read-sensitive
```

但现实采样 200 个 capability manifest（`zw_brain/skill_registration/registered/*.json`）实际使用了 10 个取值：

| 取值 | 出现次数 |
| --- | --- |
| `write-critical` | 90 |
| `read-default` | 26 |
| `write-normal` | 23 |
| `read-trace` | 22 |
| `external-execution` | 14 |
| `adapter-write` | 12 |
| `write-default` | 6 |
| `read-sensitive` | 3 |
| `read-normal` | 3 |
| `read` | 1 |

如果 audit store 入口对未声明值直接 raise，会把全部业务流量打挂；如果悄悄 drop 又违反 D4「不允许无审计落库」。

## 决策

入 store 之前在 `zw_brain/shared/audit/store.py::normalize_audit_class()` 做**两段**处理：

1. **映射归一**：把历史 10 值映射到 3 级正规化值
2. **原值留底**：把原始 audit_class 写到 payload[`original_audit_class`]，不丢信息

### 映射表

| 输入 | 归一为 | 理由 |
| --- | --- | --- |
| `write-critical` | `write-critical` | 直通；契约层最高权重写动作 |
| `adapter-write` | `write-critical` | adapter 写外部状态，回滚成本高 |
| `external-execution` | `write-critical` | 外部能力包执行，跨信任域写动作 |
| `write-normal` | `write-normal` | 直通 |
| `write-default` | `write-normal` | 「未声明的写」按 normal 归类 |
| `read-sensitive` | `read-sensitive` | 直通 |
| `read-default` | `read-sensitive` | 见下「为何不留 read-normal」 |
| `read-normal` | `read-sensitive` | 同上 |
| `read-trace` | `read-sensitive` | 同上 |
| `read` | `read-sensitive` | 同上 |
| 其他/未知 | `read-sensitive` | 防御性兜底；告警 + 留 original 字段，由 reviewer 后修 manifest |

## 为什么不留 `read-normal` 一档

基线 §6.4 明确「读类只区分是否敏感」。`read-default / read-normal / read-trace / read` 在历史 manifest 里其实是**约束设计期没收敛**的产物，并不对应业务安全语义。如果在 store 里再造一档 `read-normal` 会：

1. 与 §6.4 三级模型相左，将来 reviewer 需要再处理一次
2. 引诱新写 manifest 的人继续往非标值上靠
3. 让审计仪表盘的「敏感读」窗口出现假阴性

走「一刀切到 read-sensitive + 留 original 字段」反而最稳：

- 审计层语义稳定，只盯 3 级
- 查询时如果要看「真敏感读 vs 历史误用」，可以按 `payload.original_audit_class == 'read-sensitive'` 二次过滤
- F2 / F3 之后再对 manifest 做一次性收敛 PR，把残留 7 值改为 §6.4 三级，本 ADR 不需要修改

## 为什么不在 `emit()` 入口 raise

D4 写得很清楚：「审计写入失败必须熔断」。但「audit_class 取值不在白名单」属于**契约层**问题，不是「写失败」。store 入口对不识别值做防御性归一 + 原值留底 + warning 是更稳的处理；如果直接 raise，会把所有未对齐的旧 capability 全部打挂，业务侧无法 incremental 修复。

如果将来 manifest 收敛完成（10 → 3），可以在 `scripts/check_audit_class_enum.py`（不在本 F1 scope）里把 store 入口收紧为 raise。

## 落地点

- `zw_brain/shared/audit/store.py::normalize_audit_class(raw)` — 单函数承载映射
- `zw_brain/shared/audit/store.py::AuditStore.append()` — 调用 normalize 后写库
- `zw_brain/shared/audit/__init__.py::AuditEvent.audit_class` — 默认 `read-sensitive`（防御性兜底）

## 不在本 ADR scope

- 收敛 manifest 把 10 值收回 3 值（F2 之后另开 PR）
- 推理调用 audit（已在 client 内部走 emit）
- 区块链 anchor outbox（D4 下半，本 F1 留 post_persist_hook stub，E6 实装）
