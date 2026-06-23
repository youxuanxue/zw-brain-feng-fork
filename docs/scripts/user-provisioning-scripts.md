# 用户预置脚本

## 概述

本文档描述三支用于用户和角色数据预置/同步的 Python 脚本。它们共同负责将用户从外部系统（IAM、BSP 遗留数据库）导入或同步到 zw-brain 的 PostgreSQL 数据库中。

| 脚本 | 核心职能 | 输入 | 操作表 |
|------|----------|------|--------|
| `provision_iam_users.py` | 通过 IAM API 批量创建用户，并将 iaf_sub 写入 actor_projection | CSV 文件 | actor_projection |
| `import_loggedin_users.py` | 将已登录用户的 JSON 快照导入 PostgreSQL | JSON 快照文件 | org_projection, actor_projection, actor_org_role_binding |
| `update_user_roles.py` | 从 BSP dump 中读取旧系统用户角色，按 role-mapping-manifest 映射后更新数据库角色 | BSP SQL dump + manifest JSON | actor_projection, actor_org_role_binding |

---

## 1. provision_iam_users.py

### 作用

批量在 IAM 系统中创建用户（通过 IAM API），并将创建成功的用户同步到 PostgreSQL `actor_projection` 表。支持预检校验（用户名格式、字段完整性）、IAM 创建失败容错、数据库写入失败记录。

### 用法

```bash
python scripts/provision_iam_users.py \
  --csv <CSV文件路径> \
  --token "<IAM Bearer Token>" \
  --iam-url "<IAM基础URL>" \
  [--db-url "<数据库URL>"] \
  [--tenant "<租户ID>"] \
  [--success-out <成功输出文件>] \
  [--fail-out <失败输出文件>] \
  [--dry-run]
```

### 参数说明

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `--csv` | 是 | — | CSV 文件路径，格式：`account,phone,email,password` |
| `--token` | 是 | — | IAM API 的 Bearer token |
| `--iam-url` | 是 | — | IAM 基础 URL（如 `https://cnp-jn-rgzn-inlinux-test.inspur.com:9443`） |
| `--db-url` | 否 | `ZW_BRAIN_DATABASE_URL` 或 `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain` | PostgreSQL 连接 URL |
| `--tenant` | 否 | `sd-default` | 租户 ID |
| `--success-out` | 否 | `.data/iam-provision-success.jsonl` | 成功结果输出文件 |
| `--fail-out` | 否 | `.data/iam-provision-fail.jsonl` | 失败记录输出文件 |
| `--dry-run` | 否 | false | 只校验不真正调用 IAM 和数据库 |

### 执行流程

1. **读取 CSV**：按行读取 CSV，提取 `account`/`phone`/`email`/`password`
2. **Step 1 — 预检查**：校验用户名格式（2-22 字符，仅小写字母/数字/`-`，不以 `-` 开头/结尾）及必填字段完整性
3. **Step 2 — IAM 创建**：调用 `POST {iam-url}/auth/v1/admin/root-users` 接口，Bearer token 鉴权，创建用户
4. **Step 3 — 数据库写入**：将 IAM 返回的 `id`/`accountId` 作为 `external_actor_id`，写入 `actor_projection` 表（ON CONFLICT 更新 `display_name` / `profile_json` / `updated_at`）
5. **结果输出**：成功/失败分别写入 JSONL 文件

### CSV 格式要求

```csv
account,phone,email,password
zhangsan,13800138000,zhangsan@example.com,Passw0rd!
lisi,13900139000,lisi@example.com,Passw0rd!
```

### 备注

- IAM 用户名合规正则：`^[a-z0-9][a-z0-9-]{0,20}[a-z0-9]$`
- IAM 调用间有 100ms 延迟防止限流
- DB 写入失败的用户仍会写入成功文件（因为 IAM 侧已创建成功），方便后续重试 DB 写入

---

## 2. import_loggedin_users.py

### 作用

将 `.data/export_loggedin_users_with_full_roles.json` 中的已登录用户数据导入 PostgreSQL。相比 `provision_iam_users.py`，它处理的是**已有 IAM 身份的用户**（而非新建用户），并会写入完整的三层结构：组织、用户、组织-角色绑定。

### 用法

```bash
python scripts/import_loggedin_users.py
python scripts/import_loggedin_users.py --json-path <JSON文件路径>
python scripts/import_loggedin_users.py --db-url "<数据库URL>"
python scripts/import_loggedin_users.py --dry-run
```

### 参数说明

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-path` | 否 | `.data/export_loggedin_users_with_full_roles.json` | JSON 快照文件路径 |
| `--db-url` | 否 | `ZW_BRAIN_DATABASE_URL` 或 `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain` | PostgreSQL 连接 URL |
| `--tenant` | 否 | `sd-default` | 租户 ID |
| `--dry-run` | 否 | false | 只打印不写入 |

### 执行流程

1. **Step 1 — 检查/创建组织**：确保 `org_projection` 中存在目标组织（`org_code`），不存在则插入
2. **Step 2 — 写入用户**：遍历 `users` 列表，对每个用户 upsert `actor_projection`（按 `tenant_id + external_actor_id` 匹配已存在则更新）
3. **Step 3 — 写入角色绑定**：遍历用户下的 `actor_org_role_bindings`，写入 `actor_org_role_binding` 表（按 `tenant_id + external_actor_id + org_code + role_code` 匹配已存在则更新）

### JSON 文件格式

```json
{
  "tenant_id": "sd-default",
  "org": {
    "org_code": "ORG-DEBUG-001",
    "org_name": "调试组织",
    "status": "active"
  },
  "users": [
    {
      "iaf_sub": "a1b2c3d4-...",
      "username": "zhangsan",
      "display_name": "张三",
      "org_code": "ORG-DEBUG-001",
      "role_codes": ["ROLE_SYSTEM"],
      "email": "zhangsan@example.com",
      "binding_status": "bound",
      "match_evidence": {"method": "iaf_sub", "result": "new"},
      "actor_org_role_bindings": [
        {
          "org_code": "ORG-DEBUG-001",
          "role_code": "ROLE_SYSTEM",
          "binding_status": "active",
          "source_ref": "iam:provision"
        }
      ]
    }
  ]
}
```

### 备注

- 当前预期内的典型数据：8 个用户，每个用户多个角色绑定
- `profile_json` 中记录 `source: "export_loggedin_users"` 便于追踪数据来源
- 事务全量提交，任何异常会触发 rollback

---

## 3. update_user_roles.py

### 作用

从 BSP 旧系统的 SQL dump 中解析用户角色关系，通过 `role-mapping-manifest` 将其映射到 zw-brain 的产品角色，然后更新数据库中 `actor_projection.role_codes_json` 和 `actor_org_role_binding` 表。

**适用场景**：旧平台（DSP/BSP）的用户角色数据迁移 — 需要将遗留系统中的角色关系导入到新系统的身份治理数据模型中。

### 用法

```bash
uv run python scripts/update_user_roles.py [--dry-run] [--verbose]
uv run python scripts/update_user_roles.py --dump <BSP SQL dump> --manifest <role-mapping-manifest.json> --tenant <租户ID>
```

### 参数说明

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `--dump` | 否 | `.data.bak/old/10示例数据/dump-dsp_bsp-202604271139.sql` | BSP SQL dump 文件路径 |
| `--manifest` | 否 | `tests/fixtures/m0-sd-default/role-mapping-manifest.json` | 角色映射清单路径 |
| `--tenant` | 否 | `sd-default` | 目标租户 ID |
| `--db-url` | 否 | `ZW_BRAIN_DATABASE_URL` 或本地默认 | PostgreSQL 连接 URL |
| `--dry-run` | 否 | false | 只预览不执行更新 |
| `--verbose` / `-v` | 否 | false | 输出详细信息 |

### 数据源路径（可通过参数覆盖）

| 路径 | 说明 |
|------|------|
| `../.data.bak/old/10示例数据/dump-dsp_bsp-202604271139.sql` | BSP SQL dump 文件 |
| `../tests/fixtures/m0-sd-default/role-mapping-manifest.json` | 角色映射清单（legacy 角色 → 产品角色） |
| `ZW_BRAIN_DATABASE_URL` 环境变量 | PostgreSQL 连接 URL（默认同上） |

### 角色映射逻辑（normalize_role）

1. 从 `role-mapping-manifest.json` 读取映射规则
2. 对每个旧系统角色码：
   - 若 `target_type = "tag"` 且 `target_role_code` 在产品角色白名单内，生成 `{role_code, tags_json}`
   - 若 `target_type = "role"` 且 `target_role_code` 在产品角色白名单内，直接映射
   - 不在白名单或映射不存在的角色 → 丢弃

**产品角色白名单**：
```
ROLE_ORGAN_OPERATER, ROLE_ORGAN_MANAGER, ROLE_BUSIAUDIT,
ROLE_SECURITY_AUDIT, ROLE_SYSTEM
```

### 执行流程

1. **加载 role-mapping-manifest**：读取 legacy 角色到产品角色的映射关系
2. **解析 BSP dump**：使用 `MysqldumpParser` 解析 SQL dump，提取 `pub_user`、`pub_user_role`、`pub_user_organ_role` 表
3. **计算 dump 用户角色**：按优先级合并角色来源（`pub_user_organ_role` > `pub_user_role` > `pub_user.ROLE_VALUE`）
4. **Step 4 — 清理旧系统用户角色**：
   - 对 `status = 'iam_account_missing'` 的旧系统用户：清空 `role_codes_json` 并删除所有角色绑定
   - 额外清理 status 不是 active 但仍有 binding 的旧用户
5. **Step 5 — 更新 IAM 用户角色**：
   - 对 `source_ref` 为 `iam:provision` 或 `iaf:claims` 的用户
   - 已有角色且来源不是 `iaf:claims` 的用户跳过（不覆盖手动分配的角色）
   - 按 `display_name`（不区分大小写）匹配 dump 中的 account
   - 匹配成功：更新 `role_codes_json`，删除旧 binding 并写入新 binding
   - 匹配失败：不做操作（记录为 no-match）
6. **输出最终状态**：打印数据库中角色分布统计

### 角色来源优先级（dump 解析）

```
1. pub_user_organ_role (组织 + 角色) — 最高优先级
2. pub_user_role (主组织 + 角色)
3. pub_user.ROLE_VALUE / ROLE_CODE (主组织 + 兜底字段)
```

### 备注

- SQL dump、manifest、租户 ID 和数据库 URL 均可通过命令行参数覆盖
- 使用 `source_priority = 'bsp_import_script'` 标记 binding 的来源，便于追踪
- 支持 `ON CONFLICT ... DO UPDATE`，可重复运行

---

## 四者关系

```
                  IAM API
                    │
                    ▼
    provision_iam_users.py ──────→ actor_projection [新建 IAM 用户]
                    │
                    ▼
    import_loggedin_users.py ───→ actor_projection + org_projection
                    │                + actor_org_role_binding
                    │                [导入已有 IAM 身份的用户]
                    │
                    ▼
    update_user_roles.py ───────→ actor_projection + actor_org_role_binding
                                  [从 BSP dump 同步/更新角色]
```

三个脚本覆盖了用户预置的完整链路：
1. **`provision_iam_users.py`** — IAM 保障：先在 IAM 中创建用户，再同步到本地数据库。适合**新建用户**场景。
2. **`import_loggedin_users.py`** — 数据快照导入：将已登录的用户 JSON 快照直接落库。适合**恢复/同步已存在用户**场景。
3. **`update_user_roles.py`** — 角色迁移：将旧平台（DSP/BSP）的角色关系按映射规则迁移到新平台。适合**数据迁移上线**场景。
