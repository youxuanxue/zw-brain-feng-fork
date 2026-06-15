# D59 · 折叠 B11 督办孤儿页（IA 重定位）

**类别**：IA/可见性重定位，D28 GATE · **签字**：薛娇（产品研发负责人）2026-06-15 · `decision_only`
**签字账本**：`.testing/signoff/b11-dispute-fold.signoff.yaml`

## 背景

乔布斯上帝视角重审残刀 C-H 时，H（折叠 B11 督办面）对当前代码逐条核实，原 keynote 的四条理由里三条是**测量假象**：

- **B11DisputeDetail 是零入口孤儿页**：全仓 grep 无任何 router-link/push/href/行点击指向它，仅 `router/index.ts` import+route + `route-table.md` 三处引用；父壳 `B11ComplianceOps` 不提 dispute 一字。
- **escalate 是事件式过程标记**：`objection.case.escalate`（`objection.py:_escalate_objection_case`）自写「不改 status」，非状态机一步。
- **不撞 D57**：D57 全文 grep 督办/escalate/B11 = **0**。
- **无职责分离**：escalate 角色门（ROLE_ORGAN_MANAGER+ROLE_BUSIAUDIT）与 P5 处理者**完全重合**。

## 裁决

1. **删** `B11DisputeDetail.vue` + `router/index.ts` import/route + `route-table.md` 行（零入口，删除安全）。
2. **移** 唯一独占动作「升级督办」到 `P5ObjectionDetail.vue`（异议处理方面），复用既有 `canPerformAction('objection.case.escalate', role)` 角色门。
3. `objection.case.close` 已 `P3ObjectionDetail` 双消费、不动；后端 handler/policy/状态机/能力**零改动**；reversible。
4. 签字理由 = 纯 **IA/可见性重定位**（「无权即不可见」纪律里这类要业务签字），**非**撞 D57。

## 验证

隔离 :8801 真 UI 走查：`P5ObjectionDetail`「升级督办」按钮渲染可点；`#/compliance-ops/dispute/:id` 路由已删（导航不到）。前端 typecheck/build + 全段 `scripts/preflight.sh` PASS。
