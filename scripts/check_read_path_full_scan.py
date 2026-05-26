#!/usr/bin/env python3
"""
check_read_path_full_scan.py — preflight 段 32

强约束（PR #113 教训机械化）：
    读路径上对「热表」（usage 增长无上界的事实表）做 `select(HotModel)` 后
    返回 list 时，**必须**满足以下任一条件，否则视为「全量扫表 → 内存过滤」反模式：

      (a) 链路中含 `.limit(...)`（显式分页）
      (b) 链路中含至少一个 `.where(...)` 子句的过滤维度**超出** `tenant_id == ...`
          单一条件（例如 lifecycle_status / owner_org_id / catalog_code / status
          / id 等业务维度过滤）
      (c) 同行或上一行有豁免注释 `# full-scan-ok: <理由>`（必须给出理由，禁止裸豁免）

事故案例：[PR #113](https://github.com/feng222666888/zw-brain/pull/113)
    `catalog.entry.query` 在 P5 待发布目录场景下 `CatalogRepository.list_entries`
    仅 `where(tenant_id == X)` + 无 limit，1.2 万级目录全量加载后再内存筛
    `lifecycle_status` / `source`，导致请求停在加载态。修复手段：把
    `lifecycle_status` / `owner_org_id` / `catalog_code_prefix` / `limit` / `offset`
    全部下推为 SQL 条件。本检查就是把这种「sql 上 tenant-only 后 Python 内
    筛 + 不分页」的反模式机械化拦下。

引用：
    - 架构基线 §九 数据模型（聚合是查询单位、读热点禁全量扫）
    - 架构基线 §7.3 依赖约束（domain → shared，读路径必须在 domain 层
      就把过滤条件下推到 repository SQL）
    - docs/approved/zw-brain-architecture.md 〇.1 当前真相表（本检查写入
      preflight 段 32，作为「PR #113 同类回潮防御」机械化）

检查范围（读路径 hot path）：
    - zw_brain/domain/repositories/     # 仓储层全量扫的源头
    - zw_brain/domain/*projection*.py   # snapshot 投影也走相同模式
    - zw_brain/command/handlers/        # handler 直接拼 select 的少数路径
    - zw_brain/entry/rest/              # REST 入口若直接拼 SQL（罕见）也覆盖

「热表」allowlist（默认列表 — 这些表行数随 usage 增长无上界）：
    CatalogEntryRecord, CatalogItemRecord, CatalogEntryVersionRecord,
    CatalogModelFieldRecord, CapabilityCallRecord, AuditEventRecord,
    ObjectionCaseRecord, ObjectionProcessRecord, ObjectionEvidenceRecord,
    ApplicationRecord, ApprovalCaseRecord, ApprovalStepRecord,
    ApprovalDecisionRecord, ResourceAssetRecord, ResourceChannelBindingRecord,
    DeliveryTaskRecord, DeliveryAttemptRecord, DeliveryReceiptRecord,
    AnchorOutboxRecord

不在 allowlist 的 "reference" 表（行数由枚举/角色/区域有界）：
    RegionProjectionRecord, RoleProjectionRecord, OrgProjectionRecord,
    TenantProjectionRecord, ActorProjectionRecord, CapabilityManifestRecord,
    TopicPackageRecord, CapabilityPackageRecord, ExternalObjectMappingRecord,
    AdapterRunRecord, …

变量赋值跟踪：函数体内若是
    statement = select(HotModel).where(...)
    if cond: statement = statement.where(...)
    session.execute(statement).scalars()
本检查会回收 statement 的全部链式条件做判定；**仅 unconditional 段**参与合规
（``if`` 分支内的 optional filter/limit 不算必然下发，避免参数默认 None 时假阴性）。

query builder 直接 ``return statement``（如 ``_entry_list_statement``）同样扫描，
避免 helper 返回 tenant-only 链后在调用方 ``execute`` 时漏检。

仅在 select() 的 model 是 ast.Name 时识别 — 若代码用了 `from ... import X as Y`
别名（本仓库一致用真实类名），别名形式会被跳过；如需要扩展，添加到 HOT_MODELS
或在调用点加豁免。

豁免：
    - 上一行或同行带 `# full-scan-ok: <理由>` 注释（理由必须非空，≥7 字符）
    - 测试文件 (tests/, .testing/) 默认不扫
    - adapters/legacy/ 一次性迁移区不扫（不在 4 个目标目录里）

退出码：0 = 全通过；1 = 至少一处违反

使用：
    ./scripts/check_read_path_full_scan.py
    ./scripts/check_read_path_full_scan.py --verbose

接入：scripts/preflight.sh 段 32
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 热表 allowlist — 随 usage 增长无上界
HOT_MODELS = {
    "CatalogEntryRecord",
    "CatalogItemRecord",
    "CatalogEntryVersionRecord",
    "CatalogModelFieldRecord",
    "CapabilityCallRecord",
    "AuditEventRecord",
    "ObjectionCaseRecord",
    "ObjectionProcessRecord",
    "ObjectionEvidenceRecord",
    "ApplicationRecord",
    "ApprovalCaseRecord",
    "ApprovalStepRecord",
    "ApprovalDecisionRecord",
    "ResourceAssetRecord",
    "ResourceChannelBindingRecord",
    "DeliveryTaskRecord",
    "DeliveryAttemptRecord",
    "DeliveryReceiptRecord",
    "AnchorOutboxRecord",
}

# 豁免注释 marker — 必须配理由
EXEMPTION_RE = re.compile(r"#\s*full-scan-ok\s*:\s*(\S.{6,})")

TERMINAL_LIST_METHODS = {"scalars", "all"}
TERMINAL_SINGLE_METHODS = {
    "first",
    "scalar_one",
    "scalar_one_or_none",
    "scalar",
    "one",
    "one_or_none",
}
TERMINAL_METHODS = TERMINAL_LIST_METHODS | TERMINAL_SINGLE_METHODS


def _walk_target_files(root: Path) -> list[Path]:
    """收集 4 个目标目录下需要扫描的 .py 文件。"""
    files: list[Path] = []
    repos_dir = root / "zw_brain/domain/repositories"
    if repos_dir.exists():
        files.extend(p for p in repos_dir.rglob("*.py") if "__pycache__" not in p.parts)

    domain_dir = root / "zw_brain/domain"
    if domain_dir.exists():
        # 仅扫文件名含 projection 的（snapshot/governance/dispute 投影）
        for p in domain_dir.glob("*projection*.py"):
            if "__pycache__" in p.parts:
                continue
            files.append(p)

    handlers_dir = root / "zw_brain/command/handlers"
    if handlers_dir.exists():
        files.extend(p for p in handlers_dir.rglob("*.py") if "__pycache__" not in p.parts)

    rest_dir = root / "zw_brain/entry/rest"
    if rest_dir.exists():
        files.extend(p for p in rest_dir.rglob("*.py") if "__pycache__" not in p.parts)

    return files


def _select_call_model(call_node: ast.Call) -> str | None:
    """若 call 是 `select(SomeModel)` 形式，返回 model 名字；否则 None。"""
    func = call_node.func
    if isinstance(func, ast.Name) and func.id == "select":
        if call_node.args and isinstance(call_node.args[0], ast.Name):
            return call_node.args[0].id
    return None


def _chain_attrs_and_where_args(node: ast.AST) -> tuple[list[str], list[ast.AST]]:
    """跟随 .where(...).order_by(...).limit(...) 链路；返回 (方法名顺序, 累计 where args)。

    仅向下回溯（receiver 链）；调用方负责把多段「赋值再续链」的片段合并后传入。
    """
    chain: list[str] = []
    where_args: list[ast.AST] = []
    current = node
    while isinstance(current, ast.Call):
        if isinstance(current.func, ast.Attribute):
            chain.append(current.func.attr)
            if current.func.attr == "where":
                where_args.extend(current.args)
            current = current.func.value
        else:
            break
    return chain, where_args


def _find_select_in_chain(node: ast.AST) -> tuple[str | None, ast.AST | None]:
    """沿 receiver 链回溯找 `select(HotModel)`；返回 (model_name, select_call)。"""
    cur = node
    while isinstance(cur, ast.Call):
        m = _select_call_model(cur)
        if m is not None:
            return m, cur
        if isinstance(cur.func, ast.Attribute):
            cur = cur.func.value
        else:
            break
    return None, None


def _arg_has_non_tenant_filter(arg: ast.AST) -> bool:
    """递归判定一个 where 条件是否包含 tenant_id 之外的维度过滤。"""
    # 1) Compare: Model.field == value
    if isinstance(arg, ast.Compare):
        left = arg.left
        if isinstance(left, ast.Attribute) and left.attr != "tenant_id":
            return True
        for comp in arg.comparators:
            if isinstance(comp, ast.Attribute) and comp.attr != "tenant_id":
                return True
        return False
    # 2) BoolOp (and_/or_) — 递归任一子项含非 tenant 即合规
    if isinstance(arg, ast.BoolOp):
        return any(_arg_has_non_tenant_filter(v) for v in arg.values)
    # 3) Call: and_(...), or_(...), Model.field.in_(...), Model.field.like(...)
    if isinstance(arg, ast.Call):
        if isinstance(arg.func, ast.Attribute):
            recv = arg.func.value
            if isinstance(recv, ast.Attribute) and recv.attr != "tenant_id":
                return True
        if any(_arg_has_non_tenant_filter(a) for a in arg.args):
            return True
        return False
    # 4) UnaryOp: ~Compare 之类
    if isinstance(arg, ast.UnaryOp):
        return _arg_has_non_tenant_filter(arg.operand)
    # 5) Attribute: 单个属性引用
    if isinstance(arg, ast.Attribute):
        return arg.attr != "tenant_id"
    # 其他形式（Name / Constant）—— 保守视为合规（避免误伤）
    return True


def _comparator_is_only_tenant(args: list[ast.AST]) -> bool:
    """True = 仅含 tenant_id；False = 含至少一个非 tenant_id 业务维度。"""
    if not args:
        return True
    return not any(_arg_has_non_tenant_filter(a) for a in args)


def _line_exempted(lines: list[str], lineno: int) -> str | None:
    """检查 lineno（1-based）所在行 / 上方 ≤20 行是否带 # full-scan-ok 豁免。"""
    idx = lineno - 1
    candidates: list[str] = []
    if 0 <= idx < len(lines):
        candidates.append(lines[idx])
    for k in range(1, 21):
        if 0 <= idx - k < len(lines):
            candidates.append(lines[idx - k])
        else:
            break
    for line in candidates:
        m = EXEMPTION_RE.search(line)
        if m:
            return m.group(1).strip()
    return None


def _build_parent_map(root: ast.AST) -> dict[ast.AST, ast.AST]:
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return parent


def _inside_if(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> bool:
    """True when *node* sits under an ``if`` in the same function scope."""
    cur: ast.AST | None = node
    while cur in parent:
        cur = parent[cur]
        if isinstance(cur, ast.If):
            return True
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return False
    return False


def _iter_function_body_nodes(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """函数体节点（不含嵌套 def/class 子树），避免 ast.walk(func) 串台。"""
    out: list[ast.AST] = []

    def walk_stmt(stmt: ast.AST) -> None:
        out.append(stmt)
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            walk_stmt(child)

    for stmt in func.body:
        walk_stmt(stmt)
    return out


def _collect_function_statement_chains(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: dict[ast.AST, ast.AST],
) -> dict[str, list[tuple[ast.Call, bool]]]:
    """收集函数体内的语句链：name -> [(Call 节点, conditional?)]。

    支持模式：
        statement = select(HotModel).where(...)               # 起点
        if cond:
            statement = statement.where(...)                  # 续链（conditional）
        statement = statement.order_by(...).limit(n)          # 续链

    ``if`` 分支内的续链标记为 conditional；合规判定只看 unconditional 段，
    避免「参数默认 None 时仍是 tenant-only 全扫」被 optional filter 假阴性放过。
    """
    name_chains: dict[str, list[tuple[ast.Call, bool]]] = {}
    for node in _iter_function_body_nodes(func):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        conditional = _inside_if(node, parent)
        model, _ = _find_select_in_chain(value)
        if model is not None:
            name_chains[target_name] = [(value, conditional)]
            continue
        cur: ast.AST = value
        while isinstance(cur, ast.Call):
            if isinstance(cur.func, ast.Attribute):
                cur = cur.func.value
            else:
                break
        if isinstance(cur, ast.Name) and cur.id == target_name and target_name in name_chains:
            name_chains[target_name].append((value, conditional))
    return name_chains


def _classify_chain_segments(
    segments: list[tuple[ast.Call, bool]],
    *,
    unconditional_only: bool = False,
) -> tuple[str | None, bool, bool]:
    """对一段 statement 的多段 Call 求 (hot_model, has_limit, only_tenant)。"""
    hot_model: str | None = None
    has_limit = False
    where_args_all: list[ast.AST] = []
    for seg, conditional in segments:
        if unconditional_only and conditional:
            continue
        chain, where_args = _chain_attrs_and_where_args(seg)
        if "limit" in chain:
            has_limit = True
        where_args_all.extend(where_args)
        if hot_model is None:
            m, _ = _find_select_in_chain(seg)
            if m is not None:
                hot_model = m
    only_tenant = _comparator_is_only_tenant(where_args_all)
    return hot_model, has_limit, only_tenant


def _find_terminal_calls(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    """收集函数体内所有以 TERMINAL_METHODS 为终端的 Call（不含嵌套 def）。"""
    out: list[ast.Call] = []
    for node in _iter_function_body_nodes(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in TERMINAL_METHODS:
            out.append(node)
    return out


def _resolve_terminal_to_chain(
    terminal: ast.Call,
    name_chains: dict[str, list[tuple[ast.Call, bool]]],
) -> tuple[str | None, bool, bool] | None:
    """给定一个终端 .scalars()/.first()/... 节点，回到 select(HotModel) 段并分类。

    返回 (hot_model, has_limit, only_tenant) 或 None（无法 follow / 不是 HotModel）。
    """
    if not isinstance(terminal.func, ast.Attribute):
        return None
    terminal_attr = terminal.func.attr
    # 单行查询跳过（first/scalar_one*）
    if terminal_attr not in TERMINAL_LIST_METHODS:
        return None

    # receiver 应是 .execute(...) 调用
    receiver = terminal.func.value
    if not isinstance(receiver, ast.Call):
        return None
    if not (isinstance(receiver.func, ast.Attribute) and receiver.func.attr == "execute"):
        # 其他链式 — 直接当 chain_root
        chain_root: ast.AST = receiver
    else:
        if not receiver.args:
            return None
        chain_root = receiver.args[0]

    # case 1：chain_root 是 inline Call —— 直接分类该单段；若 receiver 链最终到的
    # Name 出现在 name_chains，把外层这段当做对该 statement 的续链一并参与判定
    if isinstance(chain_root, ast.Call):
        # 找 receiver 链顶
        cur: ast.AST = chain_root
        while isinstance(cur, ast.Call):
            if isinstance(cur.func, ast.Attribute):
                cur = cur.func.value
            else:
                break
        if isinstance(cur, ast.Name) and cur.id in name_chains:
            segments = name_chains[cur.id] + [(chain_root, False)]
            return _classify_chain_segments(segments, unconditional_only=True)
        hot, has_limit, only_tenant = _classify_chain_segments([(chain_root, False)], unconditional_only=True)
        if hot is None:
            return None
        return hot, has_limit, only_tenant

    # case 2：chain_root 是 Name —— 找 name_chains 重建多段
    if isinstance(chain_root, ast.Name) and chain_root.id in name_chains:
        return _classify_chain_segments(name_chains[chain_root.id], unconditional_only=True)

    return None


def _find_return_builder_violations(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    name_chains: dict[str, list[tuple[ast.Call, bool]]],
    lines: list[str],
) -> list[tuple[int, str, str]]:
    """query builder 直接 ``return statement`` 且 unconditional 仅 tenant 时违规。"""
    violations: list[tuple[int, str, str]] = []
    for node in _iter_function_body_nodes(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        segments: list[tuple[ast.Call, bool]] | None = None
        if isinstance(node.value, ast.Name) and node.value.id in name_chains:
            segments = name_chains[node.value.id]
        elif isinstance(node.value, ast.Call):
            if _find_select_in_chain(node.value)[0] is not None:
                segments = [(node.value, False)]
        if segments is None:
            continue
        hot_model, has_limit, only_tenant = _classify_chain_segments(segments, unconditional_only=True)
        if hot_model not in HOT_MODELS:
            continue
        if has_limit or not only_tenant:
            continue
        lineno = node.lineno
        if _line_exempted(lines, lineno):
            continue
        snippet = lines[lineno - 1].strip() if 0 <= lineno - 1 < len(lines) else ""
        violations.append((lineno, hot_model, snippet))
    return violations


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """扫描单文件，返回违规列表 [(lineno, model, snippet), ...]。"""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return violations
    lines = text.splitlines()

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parent = _build_parent_map(func)
        name_chains = _collect_function_statement_chains(func, parent)
        for terminal in _find_terminal_calls(func):
            classified = _resolve_terminal_to_chain(terminal, name_chains)
            if classified is None:
                continue
            hot_model, has_limit, only_tenant = classified
            if hot_model not in HOT_MODELS:
                continue
            if has_limit or not only_tenant:
                continue
            lineno = terminal.lineno
            if _line_exempted(lines, lineno):
                continue
            snippet = lines[lineno - 1].strip() if 0 <= lineno - 1 < len(lines) else ""
            violations.append((lineno, hot_model, snippet))
        for lineno, hot_model, snippet in _find_return_builder_violations(func, name_chains, lines):
            violations.append((lineno, hot_model, snippet))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--root", default=None, help="repo root (default: auto)")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else REPO_ROOT

    files = _walk_target_files(root)
    if args.verbose:
        print(f"[read-path-full-scan] scanning {len(files)} files under 4 target dirs")

    total_violations = 0
    files_with_violations = 0
    for path in files:
        viols = _scan_file(path)
        if not viols:
            continue
        files_with_violations += 1
        total_violations += len(viols)
        rel = path.relative_to(root)
        print(f"\n  FAIL {rel}")
        for lineno, model, snippet in viols:
            print(f"      L{lineno} [{model}] {snippet[:140]}")
            print("           reason: hot 表 list 查询仅 where(tenant_id) 且无 .limit() — 全表扫风险")
            print("           fix:    下推业务过滤到 SQL (lifecycle_status / owner_org_id / catalog_code 等)")
            print("                   或加 .limit(N) 分页；如确实需要全表扫，加豁免注释")
            print("                   # full-scan-ok: <≥7 字符理由>")

    print()
    if total_violations == 0:
        print(f"[read-path-full-scan] OK: scanned {len(files)} files, no hot-table tenant-only full-scan detected")
        print("  policy: read-path 上 select(HotModel).where(tenant_id==X) 必须 .limit() 或额外过滤维度")
        print("  case: PR #113 — catalog.entry.query 全表扫 → SQL 过滤化")
        return 0
    print(f"[read-path-full-scan] FAIL: {total_violations} violation(s) across {files_with_violations} file(s)")
    print("  policy: 读路径热表查询禁止全量扫表后内存过滤；下推为 SQL 条件或加 .limit() 分页")
    print("  case: PR #113")
    return 1


if __name__ == "__main__":
    sys.exit(main())
