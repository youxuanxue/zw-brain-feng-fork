# 排障日志 runbook

> 配套基建：`zw_brain/shared/logkit/`（feature: `infra-logging`）。
> 本文是"出了问题怎么用日志定位"的操作手册，不是设计文档。

## 1. 日志 vs 审计总线 —— 先分清两条线

| | 排障日志（logkit） | 审计总线（D4） |
|---|---|---|
| 目的 | 排查问题 | 合规记录 / 回放 / 追责 |
| 落点 | 日志文件 / stderr | audit_event 表（DB） |
| 失败语义 | 可丢，绝不阻塞业务 | 写失败熔断业务（raise） |
| 查询面 | grep / jq / tail | B1 查审计页面（audit.list 等） |

红线：日志层**绝不**写业务库（段 25）；审计失败的 raise **绝不**被日志降级（段 7a，
`CapabilityLogMiddleware` 只旁观 re-raise）。

## 2. 配置速查（env，全部可选）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ZW_BRAIN_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR；静态资源 access log 在 DEBUG 档 |
| `ZW_BRAIN_LOG_FORMAT` | `text` | 控制台格式 text\|json；**文件落盘恒为 JSON lines**，不受此影响 |
| `ZW_BRAIN_LOG_DIR` | 空 | 留空=不落盘；start-local.sh 默认注入 `.data/logs` |
| `ZW_BRAIN_LOG_FILE_MAX_BYTES` | 10485760 | 单文件上限，RotatingFileHandler 轮转 |
| `ZW_BRAIN_LOG_FILE_BACKUP_COUNT` | 5 | 轮转保留份数（每服务封顶 ~60MiB，可随时整目录删） |
| `ZW_BRAIN_CLIENT_LOG_MAX_PER_MINUTE` | 60 | /api/client-logs 进程级限流 |

两种 profile：

- **本机 dev**：`start-local.sh` 自动设 `ZW_BRAIN_LOG_DIR=.data/logs`，控制台人读格式 + 文件 JSON lines 双写。
- **容器/生产**：不设 `ZW_BRAIN_LOG_DIR`、设 `ZW_BRAIN_LOG_FORMAT=json` → 结构化日志走 stdout/stderr 由容器运行时收集（`docker logs`）；需要文件时挂卷再设 `ZW_BRAIN_LOG_DIR=/var/log/zw-brain`。

## 3. 日志文件地图与字段字典

`$ZW_BRAIN_LOG_DIR/{rest,mcp,a2a,cli}.log` —— 每入口一个文件，每行一个 JSON 对象：

| 字段 | 说明 |
|---|---|
| `ts` / `level` / `logger` / `service` | 时间(UTC)、级别、logger 名、入口（rest/mcp/a2a/cli） |
| `request_id` | 全链贯穿 id；`-` = 无请求上下文（后台线程） |
| `entry` / `actor` | 入口类型；已认证用户名（认证前为空） |
| `event` | 行类型：`http_access` / `capability_call` / `request_rejected` / `unhandled_error` / `client_error` |
| `method` `path` `status` `duration_ms` | http_access 行 |
| `skill_id` `is_write` `outcome` `audit_id` | capability_call 行；audit_id 可去 audit_event 表对账 |
| `exc` | 完整 traceback（仅 unhandled_error 一族） |
| `kind` `url` `component` `stack` `client_request_id` | client_error 行（前端上报） |

## 4. 一条请求怎么查（核心剧本）

1. 拿到 request_id：浏览器 DevTools → Network → 任意响应头 `X-Request-Id`（前端 postSkill
   每次调用都带 `UI-*` id；不带时服务端生成 `req-*` 并回显）。
2. 串全链：

```bash
grep '"request_id": "UI-20260610' .data/logs/rest.log | jq .
# 一个 id 串出：http_access（status/耗时）→ capability_call（skill/outcome/audit_id）
# → 若 5xx 还有 unhandled_error（完整堆栈）→ 若前端也炸了还有 client_error
```

3. CLI 链路：`zw-brain-cli <skill> --endpoint http://...` 自动注入同款 X-Request-Id，
   在服务端 rest.log 里同法可查；MCP 调用的 id 形如 `mcp-<jsonrpc-id>-<rand>`。

## 5. 常见症状 → 定位

| 症状 | 动作 |
|---|---|
| API 500 | `jq 'select(.event=="unhandled_error")' rest.log` → `exc` 即堆栈 |
| 403/权限不对 | `jq 'select(.event=="request_rejected")'` → 看 `actor` 是谁、detail 说了什么 |
| 慢请求 | `jq 'select(.duration_ms > 1000)' rest.log` → 先看 http_access 总耗时，再对 capability_call 分段 |
| 前端白屏/交互报错 | `jq 'select(.event=="client_error")'` → stack + url + 串联的 request_id |
| 写操作整体失败 | `jq 'select(.outcome | startswith("error:AuditWriteError"))'` → 审计 sink 故障，按 D4 这是熔断不是 bug |
| 日志文件没生成 | 确认 `ZW_BRAIN_LOG_DIR` 已设且可写；不可写时进程降级 console-only 并打一条 warning |

## 6. 红线（写代码时）

- 日志只记元数据：禁打密钥/token/PII/生 prompt/payload 本体；结构化 extra 经
  `logkit.redact` 掩码（密钥类复用 `sanitization` 的 key 判定 + PII 模式补充）。
- 审计失败路径永远 raise（段 7a，preflight 段 7a 守卫机械拦截"降级成 log"）。
- 新增结构化字段先加进 `logkit/formatter.py::EXTRA_FIELDS` 白名单，白名单外的
  record 属性不会进 JSON 行（防 ad-hoc 字段绕过 redaction）。

## 7. 人工走查验证（建栈后一次）

```bash
bash scripts/start-local.sh
curl -i --noproxy '*' -H 'X-Request-Id: probe-001' http://127.0.0.1:8800/health   # 回显
grep probe-001 .data/logs/rest.log | jq .                                          # access 行
# 浏览器 console 执行 Promise.reject(new Error('fe-probe'))
jq 'select(.event=="client_error")' .data/logs/rest.log                            # 上报行
```
