# WebUI 渲染债务台账（live+webui 能力「声称大堂供应、实际没渲染」）

> **触发**：2026-05-29 上帝视角穿透 PR #161（网关心跳）发现——capability manifest
> 的 `compatibility` 含 `webui` + `product_scope.status == "live"` 表示「该能力声称在
> WebUI 大堂供应」，但 `export_agent_contract.py --check` 只校验契约投影一致，**不校验
> 真有 `.vue`/`.ts` 渲染消费者**。普查全量 manifest：当前
> <!-- stat:zwbrain.webui-render-debt -->105<!-- /stat --> 个 live+webui 能力在
> `zw-brain-web/src` 下无任何字面量渲染落点——契约全绿，但没人在产品里看得见。

## 一、这是什么债

- **菜单印着「大堂供应」，厨房没给大堂做。** 能力的契约面（REST/CLI/MCP/A2A）可能都通，
  但人类在 WebUI 里看不到它。运营/审计 persona 的「felt experience」缺位。
- 网关运行状态（`ops.service.report.query`）原本是这 107 个之一；PR #161 收尾时给它接了
  B1.1「网关运行」只读面板（`B11ComplianceOps.vue`），从台账移出 → 现存
  <!-- stat:zwbrain.webui-render-debt -->105<!-- /stat --> 个。

## 二、机械守卫（段 52，baseline 棘轮）

- 脚本：`scripts/check_webui_capability_rendered.py`
- 台账：`scripts/webui_capability_rendered_exemptions.txt`（每行一个 slug + 可选 `# 理由/待办`）
- 规则：
  - **只拦净新增**：新增 live+webui 能力若无渲染消费者且不在台账 → preflight 红灯。
  - **台账过期检测**：台账登记了已被页面消费的 slug（应删）或不存在的 slug → 红灯。
- 数量防漂移：本文两处 `zwbrain.webui-render-debt` stat 由 `sync-stats.sh --check` 校验。

## 三、诚实补充（假阴性）

判定「已渲染」用的是 **slug 字面量 grep**。这有假阴性：部分能力经 **NL 加速器 /
通用派发**触达，页面里没有写死 slug 字面量。因此本台账是「**疑似未渲染**」，不是
「铁定死能力」。

**还债两条路**（二选一，逐步把台账清零）：
1. 给该能力接真实面板/组件渲染它——接好后**从台账删除该行**（否则守卫报「台账过期」）。
2. 确认它确经 NL 可达——在该行 `#` 后标注「NL 可达 + 入口页」理由，作为长期合理豁免。

## 四、禁止

- 禁止为消红灯把新能力**随手塞进台账而不写理由**。新增豁免须 PR 描述说明（同 D17/D33
  「软规则配套机械检查」原则——这条守卫本身就是把「契约≠产品」这个软问题硬化）。
