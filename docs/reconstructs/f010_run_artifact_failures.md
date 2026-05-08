# F-010 Run Artifact（环境阻断原文）

## 1) pytest 失败原文

```bash
$ python -m pytest
(eval):1: command not found: python
```

```bash
$ python3 -m pytest
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest
```

## 2) ruff 失败原文

```bash
$ ruff check .
(eval):1: command not found: ruff
```

```bash
$ python3 -m ruff check .
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named ruff
```

## 3) scripts/preflight.sh 通过原文（完整）

```bash
$ bash scripts/preflight.sh
preflight: repo root = /Users/xuejiao/Desktop/History/inspur/cowork/zw/zw-brain

=== branch naming (prototype/|feature/|fix/|chore/|docs/|merge/|cursor/|main|master) ===
  ok: branch 'chore/ignore-xuejiao-twin-workspaces'

=== dev-rules submodule pointer is reachable on remote ===
  skip: dev-rules submodule not configured

=== dev-rules sync drift ===
  skip: dev-rules/sync.sh not available

=== agent contract drift ===
  ok: contract docs in sync with code

=== user story / test alignment ===
  ok: stories aligned with tests

=== docs/approved/ change discipline ===
  ok: docs/approved/ unchanged in this branch

=== approved-doc invariants (R1-R4 universal + R5 main/master only) ===
  ok: R1-R4: all approved-doc frontmatter invariants hold
  skip: R5 (approved_by: pending) only enforced on main/master, current=chore/ignore-xuejiao-twin-workspaces

=== doc stats vs live values (sync-stats.sh --check) ===
  ok: all stat blocks match live values

=== cloud-agent env consistency (tools + secrets, both local and cloud) ===
  skip: .cursor/cloud-agent.env not present (cloud-agent contract not declared for this project)

=== preflight: PASS ===

=== 段 7a audit-must-block (D4) (scripts/check_audit_must_block.py) ===

[audit-must-block] OK: scanned 73 files, no audit-swallow handlers detected
  ok: audit-must-block (D4)

=== 段 7b blockchain-async (D4) (scripts/check_blockchain_async.py) ===

[blockchain-async] OK: scanned 14 business-path files, no sync await on blockchain adapter
  ok: blockchain-async (D4)

=== 段 9 fixture-pii (D11) (scripts/check_fixture_pii.py) ===
[fixture-pii] skip: .testing/fixtures/ not yet created (Phase 0 / Phase 1 task)
  ok: fixture-pii (D11)

=== 段 10 no-direct-llm (D6) (scripts/check_no_direct_llm.py) ===

[no-direct-llm] OK: scanned 333 files, no third-party LLM SDK / host detected
  (allowed gateway: zw_brain.shared.inference.client)
  ok: no-direct-llm (D6)

=== 段 11 dashboard-readonly (D15) (scripts/check_dashboard_readonly.py) ===

[dashboard-readonly] OK: scanned 3 files in zw-brain-dashboard/, no write operations detected
  ok: dashboard-readonly (D15)

=== 段 14 external-refs (D22) (scripts/check_external_refs.py) ===
[external-refs] OK: all 4 `digital-clone-research.md §X` reference(s) (3 unique anchor(s)) resolve in external file
  ok: external-refs (D22)

=== 段 15 ui-spec-b (Spec B single theme) (scripts/check_ui_spec_b.py) ===
check_ui_spec_b: OK (Spec B tokens + no Tailwind / legacy navy in shipped WebUI)
  ok: ui-spec-b (Spec B single theme)

=== 段 16 legacy-mappers (D7+D4) (scripts/check_legacy_mappers.py) ===
[legacy-mappers] OK: 10 mappers, 10 unique adapter slugs, 11 schemas routed
  ok: legacy-mappers (D7+D4)

=== preflight: PASS (common + project stages) ===
```

## 4) 影响范围

- 本地无法执行 pytest 全量回归（`python` 缺失、`python3` 环境缺 `pytest`）。
- 本地无法执行 ruff 静态检查（`ruff` 命令缺失、`python3` 环境缺 `ruff`）。
- 不影响 `bash scripts/preflight.sh`（已通过）以及本次代码/文档改动落地。

## 5) 下一 blocker 与最小补救步骤

阻断根因：当前执行环境缺少 Python 测试与静态检查工具链（`pytest`、`ruff`）。

```bash
python3 -m pip install pytest ruff
python3 -m pytest
python3 -m ruff check .
```

说明：仅补齐缺失工具，不引入额外依赖或流程变更。
