# zw-brain User Stories Index

按 `test-philosophy.mdc` § 3 规范维护。每条故事必须满足：

| # | 字段 | 要求 |
|---|---|---|
| 1 | ID | 全局唯一（`US-NNN`） |
| 2 | Title | 故事简称 |
| 3 | As a / I want / So that | 用户叙事 |
| 4 | Trace | 来源轴线（角色×能力 / 实体生命周期 / 系统事件 / 防御需求） |
| 5 | Risk Focus | 覆盖的风险类型（逻辑/回归/安全/运行时） + 具体场景 |
| 6 | Acceptance Criteria | Given/When/Then，必含正向 + 负向 + 回归保护 |
| 7 | Assertions | 可观测断言 |
| 8 | Linked Tests | `file::TestFunction` 格式 + 可执行运行命令 |
| 9 | Evidence | 输出归档路径（`attachments/`） |
| 10 | Status | Draft → Ready → InTest → Done / Archived |

## 故事清单

| ID | Title | Status | Path |
|----|----|----|----|
| _(Phase 0 早期：暂无故事；Phase 1 起按设计基线 §三 K1-K12 / N1-N7 拆解逐条建立)_ | | | |

## 命名约定

- 故事文件：`stories/US-<3 位编号>-<kebab-case>.md`，编号全局唯一
- 测试函数：`TestUSxxx_ScenarioName`
- 测试文件：`usXXX_slug_test.{go,py,ts}`
- 证据归档：`attachments/`

## 质量门禁

提交前由 `verify_quality.py` 自动校验：可执行命令 ✓ / 负向场景 ✓ / 可观测断言 ✓ / 风险类别 ✓。
报告输出到 `attachments/story-quality-report.md`。

接入：`scripts/preflight.sh` 段 5（dev-rules 模板调用）。
