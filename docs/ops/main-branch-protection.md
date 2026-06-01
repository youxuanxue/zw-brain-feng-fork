# main 分支保护 — require-CI-green（A-lite，闭合 D46.g ops 待办）

> 本文件是 main 分支保护配置的**可复现真值源**（一切代码化、版本化）。
> GitHub 仓库设置是运行态；本文件记录“应是什么 + 为什么 + 怎么复现”。

## 背景：状态真值闭环 A-lite（合 D46.g，不反转架构）

D46.g 已确立：**测量轴信任锚 = 内容指纹**（非 git_sha，squash 免疫）；
`scripts/check_feature_measurement.py`（preflight 段60「绿但指纹陈旧→FAIL」）+
`scripts/gen_feature_status.py --check`（段61 字节一致）做**便宜指纹检查**，
**不需 seed、不跑 pytest**；测量**重采**（真数据 feature 需 seed + e2e）留本地手跑。

这套便宜检查**已经在 CI 跑**：`.github/workflows/ci.yml` 的 `test (py3.12)` job
在 `pytest` 前执行 `scripts/preflight.sh`（含段60/61）。也就是说“状态视图对 HEAD
说谎（绿但指纹陈旧 / feature-status.md 漂移）”在 CI 上**已是 FAIL**。

唯一缺口是：CI 红**不阻断合并**（main 无分支保护，合后变红只能靠人盯）。A-lite 即
补这一步——**开 main 分支保护 require-CI-green**，把“合后变红”升级为“合前硬阻断”。

A-lite **不做**（仍按 D46.g 延后、对应 debt 仍 external）：
- 不在 CI 内重采测量（`capture_feature_status` / `--with-e2e`）——重活、需 seed + 起栈；
  debt `feature` / `e2e` 保持 external，trigger=首客上线需“状态视图实时反映 HEAD”。
- D11 真数据回归不进 CI 门禁（独立轨，debt `d11` external）。

## 当前配置（2026-06-01 应用）

| 项 | 值 | 说明 |
|---|---|---|
| required status checks | `test (py3.12)`、`lint (ruff)`、`legacy-import-smoke` | `test` 含 preflight=段60/61 状态真值门 + 全部架构守卫 |
| strict（要求分支领先 main 才能合） | `false` | 只要求 check 绿；不强制每次 merge 前 rebase（减摩擦） |
| enforce_admins | `false` | admin 可在紧急回滚等场景绕过；常态走门禁 |
| required_pull_request_reviews | 无 | 评审走 `/xj-review`（人在环），不在分支保护层强制 |
| restrictions（限制谁能 push） | 无 | — |

> 安全检查 `dep-vulnerabilities (pip-audit)`、`secret-scan (gitleaks)`（`security.yml`）
> 暂未设为必需；如需收紧把它们加入 `contexts` 即可（见下方命令）。
> `land-signoff`（合并时落签账本）会在非 merge 事件 skip，**不可**设为必需（否则永挂）。

## 复现 / 修改命令

```bash
cat > /tmp/protection.json <<'JSON'
{
  "required_status_checks": {
    "strict": false,
    "contexts": ["test (py3.12)", "lint (ruff)", "legacy-import-smoke"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
JSON
gh api -X PUT repos/feng222666888/zw-brain/branches/main/protection --input /tmp/protection.json

# 查看当前配置
gh api repos/feng222666888/zw-brain/branches/main/protection

# 撤销保护（紧急）
gh api -X DELETE repos/feng222666888/zw-brain/branches/main/protection
```

> 改 `ci.yml` 的 job 名时（GitHub check-run 名 = `name:` 字段，如 `test (py${{ matrix.python }})`
> → `test (py3.12)`），须同步更新上面 `contexts`，否则必需 check 永远 pending 卡合并。
