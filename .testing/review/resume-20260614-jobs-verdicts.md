# 乔布斯对抗式复核裁决（重启后重做，原 background workflow 裁决已丢失）
日期: 2026-06-14 | 复核: 3 并行 review agent + supervisor 综合 + 交叉验证

## 终裁: 7 轨全 APPROVE
| 轨 | 裁决 | 备注 |
|---|---|---|
| PR-α prod-safety M5 | APPROVE | fail-closed 健壮、双因子无绕过、4 负向测试完整 |
| alembic D58 | APPROVE | 四态分支绝不 drop_all、reset 闸 fail-closed、baseline 对称 75 表 |
| PR-5 guards-meta | APPROVE | PINNED 去循环 + 元守卫 8/8 自发现 + brain 死 shim AST 守卫 |
| PR-6 deadcode | APPROVE-WITH-FIX(E1) | 9 shim 删除安全(2 grep 命中=无下划线自由函数,非悬挂);需清 KNOWN_DEAD_SHIMS |
| PR-2 e2e-seams | APPROVE | 后端确读 draft_field_suggestions;状态名 'rejected' 确切 |
| PR-3 audit-objection | APPROVE | escalate 事件式不改 status 对齐 feature:46;角色多授诚实记 external debt;reject_reason 后端读 |
| PR-4 reco-pii | APPROVE | shared_type=3 两入池路径排除;mask 幂等;AST chokepoint |

## 组装期 2 处真实编辑
- E1: PR-6 scripts/check_brain_no_cross_cutting.py → KNOWN_DEAD_SHIMS = frozenset()（PR-5 建台账登记的 2 shim 已被 PR-6 删,须清,否则守卫「台账过期」FAIL）
- E2: docs/decisions/alembic-migration-reintroduction-D58.md:121 → 历史 R1-R8 引用加 retrofit marker（no-legacy-role-codes 守卫）

## 交叉验证 PASS
后端状态名/reject_reason 读取/alembic 入 pyproject/段20 反正则移除/escalate debt 诚实 — 全部核实通过。

## 集成冲突(组装内部消化)
- PR-1∩PR-5: scripts/check_grep_guards_batch.py 同改 → PR-β 内合一次
- PR-5↔PR-6: KNOWN_DEAD_SHIMS 台账 ↔ shim 删除 → E1 收口
- PR-α∩alembic: docs/deployment/docker-image-deployment.md → 不同节,组装时核

## 非阻塞建议(defer)
- PR-4 _no_share_resource_codes O(n) 遍历可改 SQL 过滤(性能,后续)

## e2e 全量重采抓出 2 个回归（对抗式复核漏判，重采兜住）
重采(--with-e2e)后 44→41 绿，3 feature 掉绿。clean-main+同 seed 对照证明=我方回归（非 seed）：
1. **PR-4 Part B 过度脱敏**（已回退）：redact_webui_snapshot 末端盲 mask_default 把展示用裸 `name` 键
   （资源/目录发布队列标题、字段名）当 PII 脱敏 → publish_queue 按标题定位失败 + B2 字段回显挂。
   根因：裸 `name` 既是 PII 人名又是展示标题，整树盲脱敏无上下文。回退盲兜底（per-projection 脱敏
   覆盖 PII 已足，=main 已验证行为），删守卫/测试/段69，记 debt pii-snapshot-chokepoint-overmask。
   复核教训：PR-4 reviewer 只测了 mask 幂等(对已脱敏 PII 再脱)，没测「脱敏非 PII 展示字段」——e2e 兜住。
2. **PR-3 驳回 UI 改动致 e2e spec 陈旧**（已修 spec）：P5FieldDecisionDetail 驳回从一键(硬编码理由)改两步
   (填理由→确认驳回)，但跨切 spec p0_feedback_0611_chain.spec.ts 链路2 还用旧一键 → toast 不触发。
   更新 spec 为两步 + testid 精确定位。并行隔离遗漏(PR-3 agent 没动这个跨切 spec)。
修复后 3 spec(b2×2 + p0×2) 全绿，重采回 44。
