# 场景 3：外部 Agent 通过 MCP 调用 zw-brain（§4 / §5 / §6）

**角色**：陈工，省政务大数据局技术架构组，负责设计「省级一网统办」的智能客服 Agent。客服 Agent 需要在用户问「我的低保金什么时候到账」时，跨市级政务大脑查询审批状态。

**目标**：用 1 小时评估「能不能让客服 Agent 通过 MCP 直连各市政务大脑、不用为每市单独写适配代码」。

**对应架构主张**：
- §6「Agent 是一等公民」+ 4 入口对等（Web / CLI / MCP / A2A）
- §5 Skill manifest 标准化、可发现、契约清晰
- §6.3 MCP server 暴露与 WebUI 完全相同的 Skill 集（同一套契约）
- 区别于「裸对话框入口」（N6）：Agent 走的是有契约的 Skill，不是聊天

> **原型范围说明**：场景 3 的 4 个页面在生产环境**不算 §7.3 的 10 页 WebUI**——它们是给开发者看的"Skill 契约文档站"（类似 Swagger UI），定位类比「平台开放门户」而非「业务办理界面」。原型在这里用 Web 形式呈现是为了让 GATE-1 评审能用同一个浏览器、同一套交互验证「4 入口对等」这个抽象主张。

---

## 旅程

**第 1 页：入口选择**
陈工打开 `https://zw-brain.gov.local/openapi`（原型里点顶部「Agent 入口」即到）。页面没有「请输入您的问题」聊天框——只有 4 张并排的卡片：

- **Web UI**（人类操作员用，跳转主 WebUI）
- **CLI**（运维 / 数据工程师用，左侧示例：`zw-brain skill invoke catalog.search --q "低保"`）
- **MCP**（Agent / IDE 集成用，左侧示例：`{"server": "zw-brain", "endpoint": "wss://..."}`)
- **A2A**（其他大脑 / Agent 平台用，左侧示例：Agent Card JSON 片段）

每张卡片下方都标着「**契约源**：`docs/agent_integration.md`（自动生成）」。陈工点 MCP 卡。

**第 2 页：Skill 清单**
进入 MCP 视角的 Skill 浏览器。左侧是按域分组的目录树（catalog / request / exchange / dispute / compliance / zone / dashboard / runtime），点开 catalog 看到 4 个 Skill：`catalog.search` / `catalog.register` / `catalog.update` / `catalog.deprecate`。每行有 Skill 名、一句话描述、当前版本、被订阅次数（社会证据）。

陈工搜「低保」，过滤出 3 个相关 Skill：`catalog.search` / `request.status.query` / `national.relay.query`。他点 `request.status.query`。

**第 3 页：Skill 契约详情**
页面分四区：
1. **manifest 元数据**（version / 拥有者 / 稳定性 / 鉴权要求）
2. **input schema**（JSON Schema，含字段说明 + 示例值）
3. **output schema**（同上）
4. **同一 Skill 的 4 种调用方式并列展示**（Web / CLI / MCP / A2A 各一段代码片段）—— 这就是「4 入口对等」的可视化证据：**同一 Skill ID + 同一 schema + 4 种 surface**。

底部：「**模拟调用**」按钮 + 一段填好示例参数的 JSON。

**第 4 页：模拟调用 + mock 响应**
陈工把示例 JSON 里的 `request_id` 改成自己测试用的 `REQ-DEMO-001`，点「模拟调用」。0.3 秒后下方出现：
- **请求**（实际发出的 MCP message）
- **响应**（mock 返回 `{"status": "approved", "approved_at": "2026-04-15T10:23:00+08:00", "data_url": "..."}`）
- **审计与上链**（`audit_id: AE-mock-...`、`chain_anchor: 0xmock-...`）—— 即使是 Agent 调用，写操作的合规留痕路径**完全相同**

陈工合上电脑，跟领导汇报：「能直接用 MCP 接，不用为每市单独写适配。1 个客服 Agent 适配 16 个地市，预计省 80% 集成成本。」

---

## 验证什么

- ☐ 「Agent 入口」单独成区是否正确（vs 混在 WebUI 里做"开发者文档"标签页）
- ☐ 「4 入口对等」用 4 段并列代码片段呈现是否够直观
- ☐ Skill 清单上「被订阅次数」这种社会证据对外部接入方是否有用
- ☐ 「模拟调用」是不是 GATE-1 必须演示的能力（vs 只看契约文档够不够）
- ☐ 是否需要在原型里演示「鉴权失败」的负面流（让外部接入方理解 ACL 边界）
