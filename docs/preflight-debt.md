# Preflight 缺口登记

> 当 `scripts/preflight.sh` 中某一段因「实施前置条件未就绪」而 skip 时（区别于按设计跳过 —— 例如非 main 分支不跑 approved-discipline），必须在此登记，并设定截止日期。
> 规则来源：`agent-contract-enforcement.mdc` §"Hard Constraint Wiring" 与 `dev-rules-convention.mdc` §"强约束门禁"——「禁止悄悄降级为'靠自觉'」。

## 当前缺口


| 段号   | 检查                 | 当前状态 | 缺口原因                                                                                                | 截止 / 触发条件                                                                                                                                                    | 负责人       |
| ---- | ------------------ | ---- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| 段 9  | `fixture-pii`      | skip | `.testing/fixtures/` 目录尚未创建（Phase 1 才会加载 fixture）                                                   | Phase 1 GATE-2 通过、首批 fixture 落盘当天必须激活（即创建首个 `*.json` 时该检查自动启用，无需改脚本）                                                                                         | xuejiao02 |
| 段 12 | `fixture-coverage` | 未接入  | `scripts/check_fixture_coverage.py` 尚未实现（基线 §十四 D18 决策；其前置依赖 = 段 9 fixture-pii 先有 fixture 数据可统计覆盖率） | GATE-2 通过后第 1 周内：先建脚本（覆盖率统计逻辑），再在 `scripts/preflight.sh` 追加 `run_check "段 12" ...`；`docs/approved/zw-brain-architecture-v4-gpt55.md` 附录 C 中相关映射也应同步更新 | xuejiao02 |


## 已自动启用的段（备查）

下列段在 GATE-1 已落盘并随每次 commit 实际运行，不属于「缺口」（来源：基线 §13.1 + 实际 `scripts/preflight.sh` 输出）：

- **通用模板段**（`dev-rules/templates/preflight.sh`）：段 1（branch naming）、段 2（submodule pointer）、段 3（sync drift）、段 4（contract drift）、段 5（story / test alignment）、段 8（stat drift）。
- **项目特有段**（`scripts/preflight.sh` 追加）：段 7a（audit-must-block）、段 7b（blockchain-async）、段 10（no-direct-llm）、段 11（dashboard-readonly）、段 14（external-refs，基线 §十四 D22 引入）。原段 13（gate1-prototype，D21）已下线（不再强制可点击 SPA）；`prototype/capability-sheets/` 与 `prototype/storyboards/` 仍保留为产品文档，与门禁无关。若 approved 附录 C 再出现“段 13 已 wired”当前态表述，视为文档漂移，应同步改为“已退役”。

## 与 dev-rules 分工（本仓库脚本是否「上提」共用）


| 层级                    | 内容                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **已在 dev-rules**      | `templates/preflight.sh` 通用段、`export_agent_contract --check` 契约模式、`sync-stats`、`verify-rules.sh` 等跨项目门禁。            |
| **保留在本仓库 `scripts/`** | 绑定 `zw_brain/`、`zw-brain-dashboard/`、`docs/approved/`、本子模块内 `digital-clone-research.md` 等的检查；硬编码产品路径与基线编号（D4/D6/…）。 |
| **若要上提到 dev-rules**   | 需把路径与策略改成**配置驱动**（env 或 yaml）并在模板中**可选启用**，再在 dev-rules 发版本；在未抽象前整块搬迁会强迫其它仓库接受 zw-brain 专有假设。                       |


**候选可抽象**：与目录名无关、仅 AST/正则的策略（例如「审计不得静默吞错」一类）——可先抽成 `dev-rules/scripts/` 中的库，再由各项目 `run_check` 调用；仍以各项目 `preflight.sh` 决定是否启用。

---

## 不在本表的 skip（按设计行为，非缺口）

下列段虽然当前输出 `skip:`，但 **由设计明确只在主干分支上生效**，不算「无法自动化」：

- 通用模板「`docs/approved/ change discipline`」段（基线 §13.1 注册为段 6）：`skip: no 'origin/main' to diff against` —— feature 分支无对照基准，主干门禁，**by-design**。
- 通用模板「`approved_by: pending` 拦截」段（紧随 approved-discipline 之后；§13.1 未单独编号）：`skip: not on main/master, or no docs/approved/` —— 仅在合入主干前最后一步生效，**by-design**。

> 规则：所有 by-design skip 不需要登记；**实施前置不就绪**导致的 skip 必须登记到上表。新增缺口时按上表格式追加一行（含截止 / 触发条件 + 负责人）。

