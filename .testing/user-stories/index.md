# zw-brain User Stories Index（dev-rules 模板入口，已让位给 Wave / Gherkin）

> **本目录已退役为新设计的入口形态来源**。
> 新设计权威源 = `.testing/waves/wave-{0..4}/features/*.feature`（Gherkin/BDD）+ `.testing/cross-cutting/*`（横切回归 / 角色矩阵 / 状态机 / 消费面投影）。
> 本文件仅保留两个职能：
> 1. 让 preflight 段 5（`scripts/preflight_common.sh:150` 调用 `verify_quality.py`）有一个可识别的入口；当 `stories/` 子目录不存在时，脚本主动 skip，不阻断 preflight。
> 2. 记录 dev-rules 模板原始的 10 字段 / 4 类质量门禁规范，作为如确需"User Story" 形态时的参考；新设计 Gherkin .feature 直接承接同等语义（详见下方对照）。

## 与新 `.testing/waves/*.feature` 的对照

| dev-rules 模板字段 | Gherkin .feature 等价位置 |
|---|---|
| ID | `.feature` 文件名（如 `j1-resource-discovery.feature`） |
| Title | `Feature: …` 第一行 |
| As a / I want / So that | `As a … / I want … / So that …`（紧随 Feature 标题） |
| Trace | `.feature` 文件头注释 `# Trace: R[1-15] / D-XX / 业务反馈 #N / 旧 xlsx 行 N` |
| Risk Focus | 由文件头 `# Priority` + `# Pages` + `# Roles` 联合表达；负向 / 回归 Scenario 默认覆盖逻辑 / 安全 / 运行时 / 行为回归四类 |
| Acceptance Criteria | `Background` + 至少一个正向 `Scenario` + 至少一个负向 `Scenario` + 至少一个回归 `Scenario` |
| Assertions | `Then` / `And` 步骤（要求可观测断言：DOM / HTTP / 审计字段 / 状态机迁移） |
| Linked Tests | Wave 实施 PR 落到 `tests/test_waveN_*.py`（pytest-bdd 或手写 GWT 风格），命名与 .feature 1:1 |
| Evidence | 实施 PR 跑 .feature 输出（截图 / curl trace / audit_event dump）；目录占位 `.testing/attachments/` |
| Status | `.feature` 文件头 `# Status: Draft \| Ready \| InTest \| Done` |

## 当前状态

- `.testing/user-stories/stories/` **不存在**（且不再创建）；verify_quality.py 主动 skip
- preflight 段 5 输出："`ok: stories aligned with tests`"（skip 路径），不阻断
- 新设计本身的质量由 `.testing/README.md` 列出的 Gherkin 写法规范保障：每个 .feature 必含 8 字段头 + 正向/负向/回归三类 Scenario + 可观测断言

## 命名约定（保留 dev-rules 模板原始描述，仅作历史参考）

- 故事文件：`stories/US-<3 位编号>-<kebab-case>.md`，编号全局唯一
- 测试函数：`TestUSxxx_ScenarioName`
- 测试文件：`usXXX_slug_test.{go,py,ts}`
- 证据归档：`attachments/`

> 上述命名约定**不适用**新 .testing/waves/ 设计；保留仅为说明 dev-rules 模板原意，避免他人误用。

## 质量门禁

提交前由 `verify_quality.py` 自动校验（仅当 `stories/` 子目录存在且有 `US-*.md` 时生效）：可执行命令 ✓ / 负向场景 ✓ / 可观测断言 ✓ / 风险类别 ✓。报告输出到 `attachments/story-quality-report.md`。

接入：`scripts/preflight_common.sh:150` 段 5（dev-rules 模板调用）。

## 维护原则

- 不在本目录新建 `stories/US-*.md` 文件；新设计请落到 `.testing/waves/wave-{0..4}/features/*.feature`
- 不修改 `verify_quality.py`（由 dev-rules 模板维护；本仓库视为只读 vendored 入口）
- 如 dev-rules 模板演进出与 Gherkin 形态对齐的新版本，再回头一并升级
