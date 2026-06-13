#!/usr/bin/env python3
"""check_adapter_write_ban.py — preflight 段 25（R-013 收紧：全 zw_brain/ 写入口守卫）.

§9.5 / 附录 C：DB 写入口收口到受控写层；handler / 非迁移 adapter / entry server 等
**不得自开 SQLAlchemy session 直写**（绕过 CardSession / repo / 审计总线，潜伏
lost-update + 旁路审计）。

R-013 两处收紧（相对原「只扫 adapters/、只锚 `session.`」实现）：
  1. **去接收者名锚定**：写 token 不再死锚字面 `session.`——`sess.add()` /
     `db_session.commit()` / `self._session.commit()` / 裸 `s.add()` 同样命中
     （换个会话变量名不再能绕过）。SQLAlchemy-distinctive token（commit/add_all/
     merge）任意接收者即命中；collision-prone token（add/delete/flush）要求接收者
     是 session-like 名，避免误伤 `set.add()` / `sys.stdout.flush()` / 键存储
     `.delete()` 等非 DB 写。
  2. **扫描面 adapters/ → 全 zw_brain/**：配显式白名单（受控写层，逐个核实见
     ``ALLOWED_WRITE_ZONES`` 注释）。

行级豁免 ``# adapter-write-ok: <理由>``——**冒号后必须有非空理由文本**（裸豁免
不生效，防「一注释了之」绕过）。

退出码：0 = 全部通过；1 = 至少一处违规。
接入：scripts/preflight.sh 段 25。
"""
from __future__ import annotations

import re
import sys

from guard_lib import iter_files, line_has_reasoned_exempt, register_grep_guard, repo_root

REPO = repo_root()

# 守卫面注册（供元守卫 check_guard_scan_surface 对账）：扫全 zw_brain/ 的 .py。
register_grep_guard(
    "adapter-write-ban",
    roots=("zw_brain",),
    extensions=(".py",),
    note="§9.5/R-013 — 受控写层之外不得自开 session 直写",
)

# ── 受控写层白名单（逐个核实确为合法 DB 写点）────────────────────────────
# - adapters/legacy/        ：一次性 legacy 迁移写（§9.5 唯一合法 adapter 写区）
# - domain/repositories/    ：ORM 仓储层——申请/审批/交付/目录/异议… upsert/update_status
#                             的权威落库点（D56 写路径单源收口到这里）
# - domain/services/        ：domain 服务编排的持久化（catalog_service / topic_package_service）
# - domain/{recommendation_rule,recommendation_engine,approval_flow_schema,
#   approval_flow_baseline,approval_flow_walker,form_schema,form_schema_nl_draft}.py
#                           ：live schema / 规则 / 审批流自有 session 持久化（domain 层写）
# - shared/database_store.py：存储原语（save_runtime_state / append_audit_event 等）
# - shared/audit/           ：审计总线落库 sink（D4 强制同步落库，不得旁路）
# - command/card_session.py ：CardSession identity map flush（三聚合唯一写会话，D56.a）
# - command/pipeline.py     ：PersistMiddleware（写路径 flush + sync + persist，D56）
# - entry/legacy_migration/ ：迁移 / 回滚 CLI 入口（一次性数据搬运，非运行时业务写）
ALLOWED_WRITE_ZONES = (
    "zw_brain/adapters/legacy/",
    "zw_brain/domain/repositories/",
    "zw_brain/domain/services/",
    "zw_brain/domain/recommendation_rule.py",
    "zw_brain/domain/recommendation_engine.py",
    "zw_brain/domain/approval_flow_schema.py",
    "zw_brain/domain/approval_flow_baseline.py",
    "zw_brain/domain/approval_flow_walker.py",
    "zw_brain/domain/form_schema.py",
    "zw_brain/domain/form_schema_nl_draft.py",
    "zw_brain/shared/database_store.py",
    "zw_brain/shared/audit/",
    "zw_brain/command/card_session.py",
    "zw_brain/command/pipeline.py",
    "zw_brain/entry/legacy_migration/",
)

# ── 写 token（去接收者名锚定，但避开 set/stream/键存储 false positive）──────
# SQLAlchemy-distinctive：任意接收者即命中（commit/add_all/merge 极少与非 ORM 碰撞）。
_DISTINCTIVE = re.compile(r"\.(add_all|commit|merge)\s*\(")
# collision-prone（add/delete/flush）：仅当接收者是 session-like 名时命中——
# 覆盖 ``session`` / ``*_session`` / ``Session`` / ``sess`` / 裸 ``s``，
# 不误伤 ``set.add()`` / ``sys.stdout.flush()`` / ``store.delete(key)``。
_SESSION_RECV = re.compile(
    r"\b\w*[Ss]ession\w*\.(add|delete|flush)\s*\(|\bsess\.(add|delete|flush)\s*\(|\bs\.(add|delete|flush)\s*\("
)
# session.execute(insert/update/delete(...)) — ORM core DML
_DML_EXEC = re.compile(r"\.execute\([^)]*\b(insert|update|delete)\b", re.IGNORECASE)
# 裸 SQL DML 字面
_RAW_DML = re.compile(r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.IGNORECASE)

EXTENSIONS = (".py",)
EXEMPT_MARKER = "# adapter-write-ok:"


def _write_token(line: str) -> str | None:
    for pat in (_DISTINCTIVE, _SESSION_RECV, _DML_EXEC, _RAW_DML):
        m = pat.search(line)
        if m:
            return m.group(0)
    return None


def _in_allowed_zone(rel: str) -> bool:
    return any(rel.startswith(z) or rel == z.rstrip("/") for z in ALLOWED_WRITE_ZONES)


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in iter_files(extensions=EXTENSIONS, roots=("zw_brain",)):
        rel = path.relative_to(REPO).as_posix()
        if _in_allowed_zone(rel):
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if line_has_reasoned_exempt(line, EXEMPT_MARKER):
                continue
            tok = _write_token(line)
            if tok:
                findings.append(f"{rel}:{lineno}: 写禁区出现写 token `{tok}` → `{stripped[:120]}`")

    if findings:
        print("§9.5 / R-013 写入口禁区违规（受控写层之外不得自开 session 直写）：", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print(
            f"\n共 {len(findings)} 处违规（scanned {scanned} files outside 白名单）。"
            f"\n受控写层白名单见脚本 ALLOWED_WRITE_ZONES（adapters/legacy + domain/repositories"
            f" + domain/services + 审批/表单 schema + database_store + audit + CardSession/Persist"
            f" + legacy_migration）。"
            f"\n修法：DB 写经 deps.repos.* / CardSession 取卡改卡（D56），不在 handler/entry 自开 session；"
            f"\n确属合法写点请加 `# adapter-write-ok: <理由>`（冒号后须有理由文本）。",
            file=sys.stderr,
        )
        return 1

    print(
        f"[OK] 写入口禁区清洁：scanned {scanned} files outside 白名单，无自开 session 写 token"
        f"（受控写层 {len(ALLOWED_WRITE_ZONES)} 个白名单）",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
