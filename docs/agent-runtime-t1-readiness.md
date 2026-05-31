# AgentRuntime T1 Readiness 预案

> 原 e4-b1 agentruntime F6 deliverable 预案（执行计划已随 D46.e 退役）；本预案不 land
> 主仓 Registry schema 字段，按架构 §8.6「触发式实现」原则准备好工具链
> spike，让 T1/T2/T3 任一触发当日 1 天内可 land。
>
> 关联：
> - 架构 §8 / §8.6 / R15：[docs/approved/zw-brain-architecture.md](approved/zw-brain-architecture.md)
> - 协议规范：[docs/agent-runtime/product-integration-guide.md](agent-runtime/product-integration-guide.md)
>   + [docs/agent-runtime/agent-runtime-api-cn.md](agent-runtime/agent-runtime-api-cn.md)
> - 触发式延后 debt entry：[docs/preflight-debt.md](preflight-debt.md) §「2026-05-24 — AgentRuntime runtime 触发式延后」
> - F4 trust_level 字段边界护栏：tests/integration/test_b12_intake.py
>   `test_trust_level_is_NOT_agentruntime_registry_field`
> - Spike 文件：`git 历史 cf9dd10^:.twin/e4-b1-agentruntime/spike/`（随 D46.e 退役，从历史取）

---

## 1. 触发条件（T1 / T2 / T3）

| 编号 | 触发事件 | 来源 | 当日动作 |
|---|---|---|---|
| **T1** | 出现首个**真实外部 Agent 接入需求**（ANP 平台 / Cursor / 第三方 IDE 任一来源提供 `AGENT.yaml`） | 业务方 PR / 客户提需求 / 集成商提单 | 立即 land Registry 4 字段 + validate/doctor + preflight 加段；24h 内 PR open |
| **T2** | 客户要求 **zw-brain 内置 Agent 以 `AGENT.yaml` 形态对外暴露** | 客户 ToB SoW / 演练反馈 | 选 1 个低风险 builtin Agent（建议 `governance.policy_candidate.list` 或 `audit.event.query`）转 `AGENT.yaml`；T1 工具链复用 |
| **T3** | **B1.2 接入扩展中心 UI 立项**（Wave 2 范围）→ §8.4 7 步流水线 UI 化 | E5 webui 重建 unblock 后产品方案立项 | T1 工具链 + B1.2 UI 嵌入；F4 已就绪 backend |

任一触发即升级为 P0 fix。三档 trigger 与 [preflight-debt.md](preflight-debt.md)
2026-05-24 entry 完全对齐——本预案是该 debt 的 **upgrade path**：debt entry
描述「未到触发不做」，本预案描述「触发当日做什么」。

---

## 2. 1-Day Land 工作清单

下表是 T1（或 T2 / T3）fire 后**最短可执行链路**。估时单位：小时。

| # | 步骤 | 命令 / 文件 | 估时 |
|---|---|---|---|
| 1 | 开分支 | `git checkout -b agentruntime-t1-fire` from `main` | 0.1 |
| 2 | 拷贝 spike 到 main | spike 文件原在 git 历史 cf9dd10^ 的 `.twin/e4-b1-agentruntime/spike/`，需从 git 历史 cf9dd10^ 取 `agentruntime_validate.py.skeleton` → `scripts/agentruntime_validate.py` + `chmod +x`；同理 `doctor` | 0.2 |
| 3 | 在 spike 骨架基础上补真实校验 | 解开 `# === T1 fire 时实装 ===` 注释，加 `import yaml` + 真实 `safe_load`；补 `Optional[str]` → `str` 严格化；补 5 条 validate_rules（见 §3）；运行 `python scripts/agentruntime_validate.py spike/sample_AGENT.yaml --json` 单步验证 | 1.5 |
| 4 | 加 Registry 4 字段到 schema | edit `zw_brain/capability_registry/runtime.py::validate_manifest()`：source_type='external-register' 分支强制 4 字段（diff 见 `spike/registry_schema_diff.json`（git 历史 cf9dd10^ 的 spike/ 取）） | 0.5 |
| 5 | 加 source_type 字段到现有 manifest schema | 把 `source_type: builtin` 缺省填充到现有 209 manifest（一次性 patch；export_agent_contract.py 可加 `--migrate-source-type` flag） | 0.5 |
| 6 | 第一个 AGENT.yaml fixture 入库 | 从 git 历史 cf9dd10^ 取 `.twin/e4-b1-agentruntime/spike/sample_AGENT.yaml` → `fixtures/agentruntime/sample-builtin.AGENT.yaml`；**移除** `_spike_marker` 段；真实 builtin Agent 业务名 + 真 capability 列表 | 1.0 |
| 7 | 加 preflight 新段 30 | `scripts/check_external_register_metadata.py`：对 source_type=external-register 强制 4 字段就位；接入 `scripts/preflight.sh`；详见 §5 反提前盖楼护栏 | 1.0 |
| 8 | 跑 preflight 全段 | `bash scripts/preflight.sh`：21 段 + 段 30 共 22 段全绿 | 0.3 |
| 9 | 跑 pytest 全量 | `pytest --tb=short`：baseline 157 + agentruntime 单测 不退化 | 0.3 |
| 10 | export_agent_contract.py --check | 5 投影面同步；209 → 209+N (N=新 external manifest 数) | 0.2 |
| 11 | 写 PR 描述 + open PR | 关联 §8.6 / debt entry / 本预案；标 `agentruntime-t1` label | 0.4 |
| 12 | 业务方 / 安全审计员 sign-off | PR comment「T1 fired by X，按预案 land」 | 异步 |

**总估时**：~6 小时主路径 + 业务方 sign-off 异步。1 天可达。

---

## 3. Registry Schema Diff 详解

详细 schema patch 见 `spike/registry_schema_diff.json`（git 历史 cf9dd10^ 的 spike/ 取）。

4 个新字段（仅对 `source_type=external-register` 强制）：

| 字段 | 类型 | 含义 | 默认 | validate 规则 |
|---|---|---|---|---|
| `runtime_spec_version` | string | AGENT.yaml schema 版本 | `anp-agent/v1.2` | enum：v1.1 / v1.2；v1（旧）拒绝 |
| `agent_yaml_ref` | string (uri-reference) | AGENT.yaml 存储引用 | — (必填) | 可解析（local file exists OR OCI ref pullable） |
| `trust_level` | string | **外部 Agent 来源信任级** | `untrusted` | enum：platform / verified / untrusted；platform 仅限 builtin |
| `workspace_required` | boolean | 是否需要 file workspace | `false` | true 时 doctor 检查 mount 配置 |

### 3.1 与 F4 `package.trust_level.update` 的语义边界

**这是本预案最重要的 contract 边界**——两个 `trust_level` 字段名一样，scope 完全不同：

| 维度 | F4 manifest `trust_level` | F6 Registry `trust_level` |
|---|---|---|
| **scope** | 能力包内置元数据 | 外部 Agent 来源信任级 |
| **枚举值** | baseline / reviewed / restricted / revoked | platform / verified / untrusted |
| **谁评估** | BUSIAUDIT / SECURITY_ADMIN（业务侧合规评估） | AgentRuntime supervisor + B1.2 管理员（接入侧来源评估） |
| **作用** | 决定能力包能否启用（业务流程层） | 决定外部 Agent 工具裁剪（运行时层） |
| **当前实现** | F4 已 land（package.trust_level.update + intake.py） | **T1 fire 前不 land**（本预案 spike） |
| **护栏** | `runtime.py::PACKAGE_TRUST_LEVELS` 元组 + 3 处文档 | 本预案 §5 + `test_trust_level_is_NOT_agentruntime_registry_field` |

**F4 已落地的合同护栏**（防 F6 land 前字段污染）：
- `tests/integration/test_b12_intake.py::test_trust_level_is_NOT_agentruntime_registry_field` —
  断言 `package.rollback` manifest 不含 `runtime_spec_version` / `agent_yaml_ref` /
  `workspace_required` 字段，trust_level 不进 manifest schema 而留在
  capability_package 表
- `runtime.py::PACKAGE_TRUST_LEVELS = ("baseline", "reviewed", "restricted", "revoked")` —
  与 Registry 4 字段不重叠

**确认护栏到位**（本 round 验收）：
```bash
$ pytest tests/integration/test_b12_intake.py::test_trust_level_is_NOT_agentruntime_registry_field -v
PASSED in <0.1s
```

T1 fire 时这条 test 必须**先**删除（因为 Registry 字段开始合法出现），并替换为
新 test：「manifest schema 包含 4 字段 iff source_type=external-register」。

---

## 4. validate / doctor 命令骨架契约

### 4.1 与既有 `scripts/export_agent_contract.py` 的差异

| 命令 | 输入 | 输出 | 守的边界 |
|---|---|---|---|
| `export_agent_contract.py` | 209 个 `registered/*.json`（zw-brain 内部 Capability） | 5 消费面投影同步 / drift 报红 | zw-brain Capability → 5 消费面投影一致性 |
| `agentruntime_validate.py`（T1 land） | 外部 `AGENT.yaml`（anp-agent/v1.x） | valid/invalid + violations 列表 | 外部 Agent → Registry 注册合法性 |
| `agentruntime_doctor.py`（T1 land） | 外部 `AGENT.yaml` | 多级诊断（OK/HINT/WARN/FAIL） + actionable fix 建议 | 外部 Agent → 生产 readiness（gateway 可达性 / workspace mount / 审核记录） |

两类命令出现在不同 PR 链路：export_agent_contract 在每次内部 capability
PR 跑；agentruntime_validate 在外部 Agent 注册 PR 跑（T1 fire 后才有）。

### 4.2 validate 输入输出契约

```bash
$ agentruntime_validate.py <AGENT.yaml path> [--json]
```

退出码：`0` valid / `1` invalid。

输出（stdout 非 json）：
```text
[validate] OK: fixtures/agentruntime/sample-builtin.AGENT.yaml
```
或：
```text
[validate] FAIL: fixtures/agentruntime/bad.AGENT.yaml
  - spec must be in ('anp-agent/v1.1', 'anp-agent/v1.2'); got 'anp-agent/v1'
  - permissions.scopes contains forbidden externalization prefix: 'tenant.create' (§8.5)
```

JSON 模式（`--json`）：
```json
{
  "valid": false,
  "spec_version": "anp-agent/v1",
  "skill_id": "external.bad-agent",
  "trust_level": "untrusted",
  "violations": ["spec must be in ...", "permissions.scopes contains ..."]
}
```

校验规则（10 条，与 spike `agentruntime_validate.py.skeleton` 一致）：
1. spec ∈ {anp-agent/v1.1, anp-agent/v1.2}
2. metadata.name + metadata.version 必填
3. tools.kind 不接受历史 'mcp' / 'skill'
4. permissions.scopes 禁区前缀（tenant. / policy. / audit. / canonical. /
   approval.case.decide / inference.direct）一律拒绝
5. model.provider 必须指向集团推理平台 gateway
6. auth.mode ∈ {static_api_key, trusted_gateway}；禁用 none
7. tenant_mode ≠ multi（与 sd-default 单租户对齐）
8. context.memory_mode ∈ {regulated_minimal, session_memory}
9. permissions.scopes 中 admin:runtime 仅允许由 ROLE_SYSTEM 持有
10. trust_level 缺省 → 默认 "untrusted"

### 4.3 doctor 输出契约

```bash
$ agentruntime_doctor.py <AGENT.yaml path> [--fix] [--json]
```

输出 4 级诊断：`OK / HINT / WARN / FAIL`。有任何 FAIL 退出码 1。

8 个诊断维度（与 spike doctor 骨架一致）：spec & metadata 完整性；
inference gateway 探活；agent_yaml_ref 解析；workspace volume 配置；
trust_level=verified 审核记录提示；admin:runtime 持有者校验；模型 provider
gateway；tenant_mode + auth.mode 与 sd-default 部署清单对齐。

---

## 5. 反提前盖楼护栏（preflight 段 30 — T1 fire 时 land）

**目标**：T1 fire 前主仓不允许出现 4 个 Registry 字段；T1 fire 后强制
external-register 类 manifest 包含 4 字段。本节描述 T1 fire 时新增的
`scripts/check_external_register_metadata.py`（**本 round 不实装**）。

### 5.1 T1 fire 前（当前阶段）

- **不实装**：`scripts/check_external_register_metadata.py` 不存在；
  `preflight.sh` 21 段不变
- **现有兜底**：F4 `test_trust_level_is_NOT_agentruntime_registry_field` test
  扫 `package.rollback` manifest 不含 3 个 Registry 字段；新加 manifest
  如果手抖塞字段，test 立刻红
- **debt 体现**：[preflight-debt.md](preflight-debt.md) 2026-05-24 entry
  「No mechanical preflight check (now)」明确这是「未到触发不做」的延后

### 5.2 T1 fire 时新增

```python
# scripts/check_external_register_metadata.py（spike 未提供；T1 fire 时新写）
# 目标：对 source_type=external-register 强制 4 字段就位；其他 source_type
# 一律不允许出现 4 字段（防字段污染）
REQUIRED_FOR_EXTERNAL = ("runtime_spec_version", "agent_yaml_ref", "trust_level")
FORBIDDEN_FOR_BUILTIN = ("runtime_spec_version", "agent_yaml_ref")
# trust_level 在 builtin manifest 允许出现（值固定 "platform"）；
# workspace_required 在 builtin 允许出现（值固定 false）
```

接入位置：`scripts/preflight.sh` 段 30；T1 PR diff 含本脚本。

### 5.3 反向校验示例

T1 fire 之前任何手抖把 Registry 字段加进 `zw_brain/capability_registry/
registered/<某 builtin>.json` 都会被 F4 既有合同 test 拦下；T1 fire 之后
段 30 接管。两道防线无缝接续，**没有 window of vulnerability**。

---

## 6. T1 Sign-off 检查表

T1 触发后下列 6 项全过才进 land（在 PR 描述中逐项打勾）：

- [ ] **validate 通过 spike sample**：`python scripts/agentruntime_validate.py fixtures/agentruntime/sample-builtin.AGENT.yaml --json` 输出 `{"valid": true, ...}`
- [ ] **doctor 给出 actionable 诊断**：`python scripts/agentruntime_doctor.py fixtures/agentruntime/sample-builtin.AGENT.yaml` 至少一条 OK + 必要的 HINT/WARN，无 FAIL
- [ ] **preflight 加段 30 不破现有 21 段**：`bash scripts/preflight.sh` 22 段全绿
- [ ] **capability projection 兼容 4 新字段不退化**：`python scripts/export_agent_contract.py --check` 0 drift；209+N manifest 全部投影同步
- [ ] **F4 合同护栏 test 已 replaced**：`test_trust_level_is_NOT_agentruntime_registry_field` 删除并替换为「manifest schema 包含 4 字段 iff source_type=external-register」test
- [ ] **业务方 + 安全审计员 sign-off**：PR comment 或 issue label

---

## 7. 本预案与 F6 / e4 plan 关系

- **本预案 = F6 deliverable**：原 e4-b1 F6 deliverable 预案（D46.e 退役）
  `actual_evidence` 字段在本 round commit 后填上：本文档路径 +
  spike 目录路径 + commit sha + 与 debt entry 交叉引用确认
- **本 round 不 land 主仓**：架构 §8.6 + debt entry 明确 trigger
  化原则；本 round 仅产出可读预案 + spike 骨架
- **T1 fire 时**：开新 round（建议挂 e6-platform-m0 workspace，因
  scripts/agentruntime_* 与生产运行时强相关，更贴近 e6 关注的「平台
  M0 现场」）；或在 e4 下一 round（如果触发场景与 B1.2 强耦合）。
  本预案 §2 的 12 步可作为 next-round goal.yaml 的 task 起点

### 7.1 与 debt entry 的交叉引用确认

[preflight-debt.md](preflight-debt.md) §「2026-05-24 — AgentRuntime runtime
触发式延后（D30 retrofit）」声明：

> **Trigger to re-evaluate** (任一触发即升级为 P0)：
> - **T1**：出现首个真实外部 Agent 接入需求 ...
> - **T2**：客户要求 zw-brain 内置 Agent 以 `AGENT.yaml` 形态对外暴露 ...
> - **T3**：B1.2 接入扩展中心 UI 立项 ...

本预案 §1 触发条件表与上述完全一致（T1/T2/T3 定义、来源、触发后动作
均对齐）。本预案 §2 工作清单是 debt entry **「升级为 P0」** 的具体执行
路径——debt entry 描述「触发即升级」，本预案描述「升级当日做什么」。

T1/T2/T3 任一 fire 后：
1. 在 debt entry 顶部加注 `## ⚠️ FIRED <date>`，指向本 round PR
2. PR land 后 debt entry 整段删除（不允许长期沉淀）
3. 本预案文档移到 `docs/agent-runtime-history-t1-fire-<date>.md` 作历史记录

---

## 附录 A — spike 文件清单

| 文件 | 用途 | T1 fire 时去向 |
|---|---|---|
| `registry_schema_diff.json`（git 历史 cf9dd10^ 的 spike/ 取） | 4 字段最小 schema patch + 校验规则 + 5 步 rollout strategy | 参考 patch；不直接拷贝（手动 apply） |
| `agentruntime_validate.py.skeleton`（git 历史 cf9dd10^ 的 spike/ 取） | validate 命令骨架（注释中标记 `=== T1 fire 时实装 ===` 段） | `cp` → `scripts/agentruntime_validate.py` + 补真实 yaml 解析 + `chmod +x` |
| `agentruntime_doctor.py.skeleton`（git 历史 cf9dd10^ 的 spike/ 取） | doctor 命令骨架（同上） | `cp` → `scripts/agentruntime_doctor.py` + 补 gateway/OCI 探活 + `chmod +x` |
| `sample_AGENT.yaml`（git 历史 cf9dd10^ 的 spike/ 取） | 最小内置 Agent 样本（含 `_spike_marker` 段） | `cp` → `fixtures/agentruntime/sample-builtin.AGENT.yaml`；**删除** `_spike_marker` 段；真实业务字段填充 |

spike 后缀 `.skeleton` 保证 Python 不可直接 import，preflight 段 27 ruff /
段 28 capability-registration 等都不会拾取；spike `_spike_marker` yaml 段
确保即使有人误 cp 也会被 validate 命令拒绝（spec marker 优先于其他校验）。
