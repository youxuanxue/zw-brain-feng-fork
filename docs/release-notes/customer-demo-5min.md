# zw-brain 5 分钟客户演示剧本

> ITEM-02 of `customer-delivery-final-mile`。配套脚本：`scripts/customer_demo_5min.sh`。

## 受众

客户老板 / CIO / 验收人员 / 工程对接人。5 分钟内看见：
**「找到数据 → 一键申请 → 审批把阀门 → 交付可证 → 审计可回放」**。

不是「演示 UI 有几个页面」，是「证明这套大脑端到端能跑通受控准入主路径」。

## 前置假设

- 已 clone `zw-brain` 仓库，并按 `docs/deployment/handover-checklist.md` 走完 venv（`python3 -m venv .venv && .venv/bin/pip install -e .`）。
- 已具备真数据：`old/10示例数据/dump-dsp_*.sql` 共 17 个 + `old/12-datastructure/*.xml`。仓内自带。
- 本机安装 `jq`、`curl`、`sqlite3`（macOS：`brew install jq`；Debian：`sudo apt install -y jq sqlite3`）。
- 8800 端口空闲。
- **仅本机演示场景**：脚本自动 export `ZW_BRAIN_DEV_IAM_BYPASS=1`，跳过 IAF/IAM 登录。**生产环境绝不要 export 这两个环境变量**——见 [`docs/preflight-debt.md`](../preflight-debt.md) `dev-iam-bypass` 条目。

## 一条命令

```bash
bash scripts/customer_demo_5min.sh
```

第一次跑会自动 import 真数据到 `.data/customer_acceptance.db`（≈ 1-2 分钟）。
之后每次跑都直接复用该 DB，5 段 curl 大约 3-5 秒完成。

完整 log 落在 `.data/customer-demo/demo-<时间戳>.log`。

## 7 段剧本

### 段 0：preflight + acceptance bootstrap（≈ 0-10 秒，第一次 1-2 分钟）

**命令**：脚本前半部分自动执行——venv 校验、jq 校验、端口空闲校验、acceptance db 校验。
如果 `.data/customer_acceptance.db` 不存在或 < 1MB，自动调用 `scripts/customer_acceptance_up.sh` 走真数据导入 + 严格校验 + 字段绑定 smoke。

**期望看到**：
```
[demo-5min] ok: venv + jq present
[demo-5min] ok: port 127.0.0.1:8800 free
[demo-5min] ok: 已有 acceptance db: .../customer_acceptance.db ( 18M)
```

**业务含义**：M0 真数据已落库——客户的 17 个旧平台 dump + 5 个 datastructure xml 已经按 sd-default 单租户单省映射到 canonical schema，**不是 mock，不是 fixture，是客户拿来的真数据**。

### 段 1：启动 REST + dev-bypass 登录（≈ 4 秒）

**命令**：脚本启动 `.venv/bin/python -m zw_brain.entry.rest.server`，等待 `/health` 200。

**期望看到**：
```
ZW_BRAIN_DEV_IAM_BYPASS=1 is active — IAM auth is fully bypassed and every request runs as a synthetic dev-iam-bypass user with all r1..r8 roles. DEVELOPMENT ONLY.
[demo-5min] ok: REST healthy @ http://127.0.0.1:8800/health
```

**业务含义**：dev-bypass 模式下，单个合成用户具备 R1-R8 全部 8 个角色，便于一条脚本演完端到端流。生产环境走 IAF/OIDC，登录后由 IAM 注入真实 role_codes——同一套 REST、同一套 skill。

### 段 2：R1 浏览真目录（catalog.browse）

**命令**：
```bash
curl --noproxy '*' "http://127.0.0.1:8800/api/skills/catalog.browse?lifecycle=all&limit=10&role=r1"
```

**期望看到**：
```json
{"total": 14, "head": [
  {"code": "cat-business", "title": "城市运行专题目录", "lifecycle_status": "approved_pending_publish", "owner_org_id": "市城市运行专班"},
  {"code": "cat-parking", "title": "停车场信息目录", "lifecycle_status": "active", "owner_org_id": "省大数据局"},
  {"code": "res-company-visit", "title": "企业走访差异补录视图", ...}
]}
```

**业务含义**：R1 业务专班视角下，从单租户 `sd-default` 看到 14 条已落库的真目录条目，每条都带 owner_org / lifecycle_status / 真实 catalog_code。**不是导航菜单——是按申请视角组织的可复用目录池**。

### 段 3：R1 看目录详情（catalog.resource_view）

**命令**：脚本自动用上一步首条 active 目录（演示中是 `cat-parking`）。
```bash
curl --noproxy '*' -X POST -H 'Content-Type: application/json' \
  -d '{"resource_id":"cat-parking","role":"r1"}' \
  http://127.0.0.1:8800/api/skills/catalog.resource_view
```

**期望看到**：
```json
{"id": "cat-parking", "name": "停车场信息目录", "status": "active", "fields_count": 0, "coverage": "真实旧平台目录"}
```

**业务含义**：R1 看到的字段/coverage/状态都来自 canonical schema，**和接下来 R2 审批、R6 交付、R8 审计看到的是同一行记录**——单一事实来源，不是 R1 一个面、R2 另一个面。

### 段 4：R1 发起复用申请（application.resource.submit）

**命令**：脚本以 R1 角色对种子资源 `res-market-activity` 发起申请，purpose = "5 分钟客户演示 — 市营商环境专班复用市场主体活跃度"。
```bash
curl --noproxy '*' -X POST -H 'Content-Type: application/json' \
  -d '{"resource_id":"res-market-activity","role":"r1","confirmed":true,"query":"..."}' \
  http://127.0.0.1:8800/api/skills/application.resource.submit
```

**期望看到**：
```json
{"ok": true, "audit_id": "AE-2026-05-18-...", "request": {"id": "REQ-2026-05-18-0002", "status": "pending"}}
```

**业务含义**：
- R1 不需要自己写 SQL/对接系统——一条申请把 purpose、scope、time_window、最小必要字段全打包成 canonical application。
- 状态进入 `pending`，**只有 R2 审批通过才进入交付链路**——这就是阀门，不是「点了就给数据」。
- `audit_id` 当场返回，方便 R8 后续回放。
- **幂等**：若已存在 pending 申请，脚本自动复用，不重复落库。

### 段 5：R2 审批通过（approval.review_decide）

**命令**：
```bash
curl --noproxy '*' -X POST -H 'Content-Type: application/json' \
  -d '{"request_id":"REQ-2026-05-18-0002","decision":"approve","role":"r2","confirmed":true}' \
  http://127.0.0.1:8800/api/skills/approval.review_decide
```

**期望看到**：
```json
{"ok": true, "audit_id": "AE-2026-05-18-...", "decision": "approve_reuse", "status": "granted"}
```

**业务含义**：
- R2 审批承接人员一条命令通过，状态从 `pending` → `granted`，自动触发交付链路。
- decision = `approve_reuse` 表明这是按「先复用真目录、不新增整表」策略通过——不是无脑放行。
- 审批 audit_id 与 R1 申请 audit_id 不同但同链，R8 可以串起来。

### 段 6：R8 审计回放（audit.list）

**命令**：
```bash
curl --noproxy '*' -X POST -H 'Content-Type: application/json' \
  -d '{"role":"r8"}' \
  http://127.0.0.1:8800/api/skills/audit.list
```

**期望看到**：
```json
{"count": 41, "tail5": [
  {"audit_id":"AE-...","type":"application.resource.submit.before","actor":"user:gov:r1:周处长[bypass]","target":"res-market-activity"},
  {"audit_id":"AE-...","type":"application.resource.submit.after","actor":"user:gov:r1:周处长[bypass]","target":"REQ-2026-05-18-0002"},
  {"audit_id":"AE-...","type":"approval.review_decide.before","actor":"user:gov:r2:刘主任[bypass]","target":"REQ-2026-05-18-0002:approve_reuse"},
  {"audit_id":"AE-...","type":"approval.review_decide.after","actor":"user:gov:r2:刘主任[bypass]","target":"REQ-2026-05-18-0002:approve_reuse"},
  {"audit_id":"AE-...","type":"audit.list.before","actor":"user:gov:r8:林督查[bypass]","target":"AE-..."}
]}
```

**业务含义**：
- R8 督查/审计角色看到 R1 提交、R2 决策、R8 自己的查询都按 before/after 双事件落库。**没有任何一次 mutation 不落审计**。
- `target` 字段串起了 resource_id → request_id → 决策，构成可机器解析的证据链。
- 区块链锚定 (`chain: pending`) 走 D4 异步 adapter——外链 down 不阻塞业务，但有 retry。

### 段 7：浏览器接管（可选，但建议演示）

**命令**：保持脚本启动的 REST 进程不停，浏览器打开：
```
http://127.0.0.1:8800/
```
首页右上『开发模式登录 dev-bypass』一键登录。

**期望看到**：进入 R1 工作台后切角色到 R2，能看到刚才那条 `REQ-2026-05-18-0002` 已在「已通过」列表；切到 R8 督查可以看到审计回放面板。

**业务含义**：5 段 curl 已经把模型层证明出来；剩下 90 秒让客户摸一下 WebUI，对应「同一套 skill 在 WebUI / REST / CLI / MCP / A2A 5 个消费面共享」——D2 单一事实来源。

## 一句话总结（脚本末尾自动打印）

```
R1 浏览到 14 条真目录条目（含 停车场信息目录 等）；
R1 看到 cat-parking 详情（0 字段）；
R1 提交申请 REQ-2026-05-18-0003；
R2 一键通过；
R8 审计回看到 53 条事件链。
浏览器入口：http://127.0.0.1:8800/  (用 dev-bypass 登录)
```

## 演示后下一步

按客户重点选 1 条递进：

- **数据范围**：跑 `bash scripts/customer_export.sh` 把 sd-default 全量真目录导出 csv 让客户看广度。
- **角色全貌**：按 [`.experiences/`](../../.experiences/) R1-R8 八角色文档，1 个角色 1 分钟扫一遍。
- **稳态运营**：走 [`docs/deployment/sd-default-onboarding.md`](../deployment/sd-default-onboarding.md) 全 41 项 handover checklist。
- **架构基线**：翻 [`docs/approved/zw-brain-architecture-v4-gpt55.md`](../approved/zw-brain-architecture-v4-gpt55.md) D1-D22 决策。

## 失败 next-step

| 现象 | next-step |
|------|-----------|
| `port 127.0.0.1:8800 already in use` | `lsof -nP -iTCP:8800 -sTCP:LISTEN` 找占用进程，kill 或换 `ZW_BRAIN_REST_PORT=8810 bash scripts/customer_demo_5min.sh` |
| `customer_acceptance_up.sh 失败` | 看其 stderr：通常是缺 `.venv` 或缺 `old/10示例数据/dump-*.sql` |
| `catalog.browse` 返回 `total=0` | 重跑 `bash scripts/customer_acceptance_up.sh` 强制重导入 |
| `application.resource.submit` 422 entity_not_found | `seed_snapshot.json` 损坏，`git checkout -- zw_brain/domain/seed_snapshot.json` |
| 任一 curl 502 Bad Gateway | 你有 http_proxy=127.0.0.1:7890 类代理污染 shell；脚本已自动 unset，但若你手动 curl 演示，加 `--noproxy '*'` |
