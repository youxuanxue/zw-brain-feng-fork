# 场景智能体 · 本地部署与使用指南（客户向）

> 面向：想在本机把平台跑起来、亲手用一下 **A① 数据发现副驾** 与 **B 试点 法人信用画像研判副驾** 的客户。
> §2 的 **REST 调用路径**所有命令与输出均已在本机实跑验证（真实 GLM-4 推理 + 真实数据库）。
> A① 本期**只经 REST/AgentRuntime 调用**（§2），其 P2 找数页内嵌副驾 UI 是 Wave-2 后续交付（见验收清单 U6）；
> WebUI（§3）本期只承载 B 类【数据应用】与平台指南副驾。
> ⚠️ 本指南是 **dev / 演示** 路径（含 IAM 免登录）。生产部署走 `docs/deployment/docker-image-deployment.md`（真实 IAF/OIDC），切勿混用。

---

## 0. 一次性前置（装好就不用再装）

```bash
# 在仓库根目录（含本场景智能体的分支 feature/scenario-agents）
cd <zw-brain 仓库根>

# (1) 数据库：PostgreSQL（已全盘 PG）
docker compose up -d postgres            # 起库（端口/凭据与默认 URL 对齐，零 env）

# (2) Python 环境 + AgentRuntime 离线 SDK（py312，跑智能体必需）
#     文档路径见 vendor/agent-runtime/README.md；若 uv venv 无 pip，用下面这套等效装法：
uv venv --python 3.12 .venv-py312
uv pip install --python .venv-py312/bin/python -e '.[dev,postgres]'
cd vendor/agent-runtime/release/v1.1.3
shasum -a 256 -c agent-runtime-1.1.3-py312-pyc-only.tar.gz.sha256   # 校验失败必停
tar -xzf agent-runtime-1.1.3-py312-pyc-only.tar.gz
cd agent-runtime-1.1.3-py312-pyc-only
uv pip install --python ../../../../.venv-py312/bin/python --find-links wheelhouse -r requirements.txt
SP=$(../../../../.venv-py312/bin/python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
cp -R python/agent_runtime "$SP/agent_runtime"
cp -R dist-info/agent_runtime-1.1.3.dist-info "$SP/"
../../../../.venv-py312/bin/python -c "from agent_runtime import RuntimeService; print('SDK OK')"
cd <zw-brain 仓库根>

# (3) 前端（首次需构建一次；start-local.sh 会自动构建，但需先装 npm 依赖）
cd zw-brain-web && npm install && npm run build && cd ..

# (4) 推理网关：cp .env.example .env，填好集团推理网关（决定智能体是否“真的会思考”）
cp .env.example .env
#   .env 里至少填：
#   ZW_BRAIN_INFERENCE_MODE=platform
#   ZW_BRAIN_INFERENCE_GATEWAY_URL=https://<OpenAI兼容网关>/...      # 如 Volcengine Ark /api/v3
#   ZW_BRAIN_INFERENCE_MODEL=<chat模型>                              # 如 glm-4-7-...
#   ZW_BRAIN_INFERENCE_API_KEY=<网关密钥>
#   不填 → 默认 mock 推理（返回 canned 文本、不会真检索推荐）。
```

---

## 1. 启动平台（一条命令）

```bash
cd <zw-brain 仓库根>
# D68 单一模型：MODE=http → start-local 起独立 agent-runtime serve（:8001）+ REST（:8800），REST 经 HTTP 驱动 AR。
ZW_BRAIN_AGENT_RUNTIME_MODE=http \
ZW_BRAIN_AGENT_RUNTIME_ENABLED=1 \
ZW_BRAIN_PYTHON_BIN=$PWD/.venv-py312/bin/python \
bash scripts/start-local.sh
# 等到日志出现：[start-local] ok: AgentRuntime healthy at http://127.0.0.1:8001/runtime/health
#               [start-local] ok: REST healthy at http://127.0.0.1:8800/health
# 并确认：[start-local] inference: ZW_BRAIN_INFERENCE_MODE=platform   ← 这行是 platform 才是真 LLM
```

- REST + WebUI 监听 `http://127.0.0.1:8800`。
- dev 模式自动免登录（IAM bypass），默认会话机构 = 省大数据局。
- 若本机设了 http(s)_proxy 导致 curl 返回 502：`export NO_PROXY=127.0.0.1,localhost`。

> **更省事（容器一把起三件套）**：装好 docker 后，`cp .env.example .env`（填推理网关）→ `docker compose up -d`
> 即同起 `postgres` + 独立 `agent-runtime`（:8001）+ `zw-brain`（:8800），免手装 py312 venv / 离线 SDK。
> `agents/` 以只读卷挂进两服务（**单一源**：AR 跑 + zw-brain 列），加 Agent 两边即时同步。详见
> `docs/deployment/docker-image-deployment.md` §1.1。⚠️ Docker **build** 需 registry 可达的环境。

---

## 2. 使用方式 A · REST API（已验证可用，推荐）

智能体是“页内嵌 / 用数方场景副驾”形态，通过 AgentRuntime REST 调用。**三步：列出 → 起任务 → 取结果。**

```bash
export NO_PROXY=127.0.0.1,localhost
B=http://127.0.0.1:8800

# (1) 看有哪些智能体
curl -s "$B/api/agent-runtime/agents" | python3 -m json.tool
#   → 返回 zw-search-helper / legal-person-credit-profiler / zw-platform-guide，各带 capability_skills

# (2) 用 A① 数据发现副驾：起一个任务（role=用数方操作员）
curl -s -X POST "$B/api/agent-runtime/tasks" -H 'Content-Type: application/json' -d '{
  "agent_id": "zw-search-helper",
  "input": "我想找企业登记和停车场相关的政务数据，有哪些可以申请？",
  "role": "ROLE_ORGAN_OPERATER"
}'
#   → {"task_id":"...","status":"pending"}   立即返回，后台真实 LLM 跑（约 30s）

# (3) 轮询取结果（用上一步的 task_id）
curl -s "$B/api/agent-runtime/tasks/<task_id>"
#   → status 从 running → completed；completed 时 final_output 即智能体产出
```

**A① 实跑真实产出（节选，数据来自真实库）：**

```text
根据检索结果，为你找到以下可申请的政务数据资源：
## 停车场相关资源（2条）
| 资源名称 | 目录编号 | 提供方 | 共享条件 | 更新频率 | 可申请 |
| 停车场信息 | 370000308004000000/000001 | 省大数据局 | 有条件共享 | 7天 | ✅ |
| 停车场信息表（五城区） | 370000307001040000/000003 | 市交通运输局 | 依申请共享 | 2天 | ✅ |
推荐理由：省级覆盖更广、市级更新更快…
## 企业登记相关资源
检索到的是“特定行业企业审批数据”，非通用企业登记 …（术语对齐 + 诚实提示）
```

**用 B 试点 法人信用画像研判副驾（role=用数方管理员）：**

```bash
curl -s -X POST "$B/api/agent-runtime/tasks" -H 'Content-Type: application/json' -d '{
  "agent_id": "legal-person-credit-profiler",
  "input": "我要对一家企业做信用风险尽调，平台上有哪些法人/登记/信用类数据可以用来研判？",
  "role": "ROLE_ORGAN_MANAGER"
}'
# 同样轮询取结果
```

**B 试点实跑真实产出（节选）：** 列出「法人登记注册基本信息 / 法人基础信息 / 山东省统一社会信用代码数据库信息（含 37 个字段：法定代表人、统一社会信用代码、经营状态、注册资金、经营范围、纳税相关…）/ 特殊法人类型」等可用研判数据，每条带目录编码、提供方、共享类型、适用场景。检索不到时**诚实说明、不编造信用分**。

> 角色很关键：B 试点要读「字段映射」类敏感能力，需 **管理员/运营/审计** 角色；基础操作员会被正确拒绝（最小权限）。A① 找数用 **操作员** 即可。

---

## 3. 使用方式 B · 浏览器（WebUI，推荐给业务用户）

浏览器打开 `http://127.0.0.1:8800` 即平台界面（dev 免登录，右上角可切换岗位走查）。两类智能体各在其位：

- **B 类 → 顶级【数据应用】**：切到**部门管理员**（或业务运营员）岗位后，左侧「用数据」分组出现【数据应用】入口（该入口仅对能调用其中应用的岗位可见——无权岗位不显示，避免点开撞 403）；进入数据应用画廊，点开「法人信用画像核验」卡片 → 进入对话工作台，直接提问、看研判（敏感字段映射需管理员/审计权限）。
- **A① 找数副驾**：本期**只经 REST 调用**（见 §2），P2 找数页内嵌副驾 UI 是 Wave-2 后续交付（验收清单 U6）；当前【找数据】页走平台既有「智能检索」，不经本 Agent。
- **平台指南副驾**（`zw-platform-guide`）仍在右下角悬浮入口可直接对话。

> 落位由后端 `/api/agent-runtime/agents` 的 `category` 字段（从 `AGENT.yaml labels.surface` 派生：`data-app` / `copilot`）驱动——单一事实源：给新数据应用打 `labels.surface: data-app` 即自动进【数据应用】画廊，无需改前端。

---

## 4. 停止 / 排障

```bash
# 停止：start-local.sh 前台 Ctrl+C；后台启动则 kill 掉 REST 进程
# 排障日志（JSON lines）：tail -f .data/logs/rest.log | jq .   （按 X-Request-Id 串全链）
```

常见点：
- 智能体回的是套话/不检索 → `.env` 没填 `ZW_BRAIN_INFERENCE_MODE=platform` + 网关，走了 mock。
- POST 报 503 `agent_runtime_disabled` → 启动时漏了 `ZW_BRAIN_AGENT_RUNTIME_ENABLED=1`。
- POST 报 404 `agent_not_found` → agent_id 拼错（用 `/api/agent-runtime/agents` 里的准确 id）。
- POST 报 403 `no_product_role_for_identity` → 带上 `"role"`（A① 用 `ROLE_ORGAN_OPERATER`，B 试点用 `ROLE_ORGAN_MANAGER`）。
- 任务 30s+ 才完成属正常（智能体认真多次检索）；REST 默认非阻塞，请用轮询，别用 `?mode=block`。

---

## 5. 与验收清单的对应

本指南让你能亲手勾掉 `customer-acceptance-checklist.md` 里的 U1–U5、B1–B3、O1（看列表）、G1（换 operator 角色试 B 试点会被拒）。U6（A① 嵌进 P2 页 UI）是明确的后续交付。
