#!/usr/bin/env python3
"""check_no_hardcoded_org_literal.py — preflight 段 70

部门数据隔离防回归硬化（承 #298 / D61）。

#298「部门数据隔离过度收口回归修复」的根因之一是**写侧把机构码写死成字面量**：
申请/编目向导把 owner_org_id / applicant_org_code 钉成一个无关机构的统一社会信用代码
（如 11370000MB284651XL「省大数据局」），导致

  - 所有运行时单的 applicant_org / owner 列对**任何登录人**恒为同一机构；
  - 部门数据隔离按 applicant_org / owner 行级过滤时（request_party_in_scope /
    org_in_scope），把申请人自己刚提的单也滤掉（「看不到自己刚建的草稿」即此根因）；
  - 与登录人 / 会话机构完全脱钩。

#298 已确立的口径：写侧机构字段一律取可信会话 ``caller_org_code(payload)``
（显式 payload['org_code'] 优先、actor_snapshot.current_org_code 回落），取不到诚实留空
（fail-closed），**绝不**回退到任何硬编码机构常量。

本守卫机械化拦住「把机构码写回字面量」这类回归：

后端写路径（硬 FAIL，近零误报——实测干净基线 0 命中）
  扫 ``zw_brain/command/handlers/**`` 与 ``zw_brain/domain/services/**`` 的 ``*.py``，
  禁止出现**统一社会信用代码字面量**（18 位 ``[0-9A-Z]`` 引号串，如
  ``"11370000MB284651XL"``）。机构字段须从 caller_org_code / 资源 owner 解析，
  不得钉死成一个具体机构。

前端 skill 调用面（review 提示，非致命——避免误伤展示用常量）
  扫 ``zw-brain-web/src/**`` 里的 18 位码字面量，**只作 review 提示输出、不拦 commit**。
  原因：前端「展示用常量」（``const defaultOwnerOrg = '…'`` 仅模板回显、不进 payload）
  是合法的、不在禁止之列（#298 已把 owner_org_id 改为后端 caller_org_code 注入，残留
  的展示常量由后续清理批 S2 收口）。「该字面量是否作为对象字面量值出现在 payload /
  owner_org_id 赋值上下文」这一判据**难以用正则在多行 Vue 模板里精确机械化**——按
  CLAUDE.md「可机械化边界」原则，不可化约的语义判断不硬造守卫（硬造=误报负债），故
  前端只列 review 项、把边界写进报错，宁可窄不可误报。

allowlist（合法放行）：``tests/`` / ``fixtures/`` / ``seed`` / ``adapters/legacy/`` 路径下
  的码字面量是真实测试 / 迁移 / 种子数据，合法。``# org-literal-ok:`` 行注释亦放行任何
  刻意例外（``#`` 或 ``//``）。

退出码：0 = PASS（后端零命中）；1 = 后端命中违规。前端 review 提示不影响退出码。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 后端写路径扫描根（硬 FAIL 面）。
BACKEND_WRITE_ROOTS = (
    REPO / "zw_brain" / "command" / "handlers",
    REPO / "zw_brain" / "domain" / "services",
)
# 前端 review 提示面。
FRONTEND_ROOT = REPO / "zw-brain-web" / "src"

# 统一社会信用代码字面量：恰好 18 位大写字母 + 数字，前后无相邻 [0-9A-Za-z_]（避免
# 截到更长的标识符 / 哈希片段中间），且整体被引号（' 或 "）直接包裹（字面量、非裸 token）。
USCC_QUOTED = re.compile(r"""(['"])(?<!\w)([0-9A-Z]{18})(?!\w)\1""")

LINE_EXEMPT = "org-literal-ok:"

# 路径级 allowlist：这些片段出现在相对路径任一段即放行（测试 / 种子 / 迁移合法）。
ALLOW_PATH_FRAGMENTS = (
    "/tests/",
    "/fixtures/",
    "/adapters/legacy/",
    "seed",  # seed_snapshot.json 等种子数据 + seed_* 脚本
)


def _is_allowed_path(rel: str) -> bool:
    lowered = "/" + rel.lower()
    return any(frag in lowered for frag in ALLOW_PATH_FRAGMENTS)


def _scan_text(text: str) -> list[tuple[int, str]]:
    """返回 [(行号, 命中码)]；命中行带 org-literal-ok: 注释则跳过。"""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if LINE_EXEMPT in line:
            continue
        for m in USCC_QUOTED.finditer(line):
            hits.append((lineno, m.group(2)))
    return hits


def _scan_tree(root: Path, suffixes: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    if not root.exists():
        return violations
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        rel = path.relative_to(REPO).as_posix()
        if _is_allowed_path(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, code in _scan_text(text):
            violations.append(f"{rel}:{lineno}: hardcoded org/USCC literal {code!r}")
    return violations


def _run_repo() -> int:
    # ── 后端写路径（硬 FAIL）──
    backend_violations: list[str] = []
    for root in BACKEND_WRITE_ROOTS:
        backend_violations.extend(_scan_tree(root, (".py",)))

    # ── 前端面（review 提示，非致命）──
    frontend_hits = _scan_tree(FRONTEND_ROOT, (".vue", ".ts", ".js"))

    if frontend_hits:
        print(
            "[no-hardcoded-org-literal] REVIEW (前端，非致命): zw-brain-web/src 下发现 18 位机构码字面量。\n"
            "  边界：前端**展示用常量**（仅模板回显、不进 skill payload）合法；只有出现在\n"
            "  invokeActionStub / postSkill 的 payload / owner_org_id 赋值上下文里才是回归面\n"
            "  （#298 catalog 向导 owner_org_id 硬编码的复发面）。本判据难以用正则在多行 Vue\n"
            "  里精确机械化，故仅列出供人工复核（CLAUDE.md 可机械化边界原则）：",
            file=sys.stderr,
        )
        for v in frontend_hits:
            print(f"    {v}", file=sys.stderr)

    if backend_violations:
        print(
            "[no-hardcoded-org-literal] FAIL — 后端写路径（zw_brain/command/handlers/** 与\n"
            "  zw_brain/domain/services/**）禁止硬编码统一社会信用代码字面量。机构字段须从可信会话\n"
            "  caller_org_code(payload) / 资源 owner 解析，取不到诚实留空（fail-closed），不得钉死\n"
            "  成一个具体机构（承 #298 / D61 部门数据隔离）。如属真实测试/种子/迁移数据请移到\n"
            f"  allowlist 路径（{', '.join(ALLOW_PATH_FRAGMENTS)}）或加 `# org-literal-ok:` 行注释：",
            file=sys.stderr,
        )
        for v in backend_violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(
        "[no-hardcoded-org-literal] OK: 后端写路径（handlers + domain/services）零硬编码机构码字面量"
        f"（前端 review 提示 {len(frontend_hits)} 处，非致命）。"
    )
    return 0


def _self_test() -> int:
    """自带回归：构造含 / 不含 18 位码的片段，断言扫描器命中 / 放行符合预期。"""
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    # 命中：payload 里赋一个 18 位码。
    bad = 'request = {"applicant_org_code": "11370000MB284651XL", "kind": "apply"}'
    check("detect-quoted-uscc", _scan_text(bad) == [(1, "11370000MB284651XL")])

    # 命中：单引号亦然。
    bad2 = "owner = '36010000123456789X'"
    check("detect-single-quote", len(_scan_text(bad2)) == 1)

    # 放行：行内 org-literal-ok 注释。
    exempt = 'x = "11370000MB284651XL"  # org-literal-ok: 测试基线锚点'
    check("honor-line-exempt", _scan_text(exempt) == [])

    # 不误伤：更长的标识符 / 哈希（19+ 位）不命中。
    long_id = 'sha = "11370000MB284651XLZ"'  # 19 位
    check("no-false-positive-longer", _scan_text(long_id) == [])

    # 不误伤：含小写的混合串不命中（USCC 全大写+数字）。
    mixed = 'token = "11370000mb284651xl"'
    check("no-false-positive-lowercase", _scan_text(mixed) == [])

    # 不误伤：18 位但未被引号包裹（裸 token）不命中。
    bare = "code = 11370000MB284651XL  # 非字符串字面量"
    check("no-false-positive-unquoted", _scan_text(bare) == [])

    # 路径 allowlist：tests/ 下放行。
    check("allow-tests-path", _is_allowed_path("tests/test_x.py"))
    check("allow-legacy-adapter", _is_allowed_path("zw_brain/adapters/legacy/m.py"))
    check("allow-seed", _is_allowed_path("zw_brain/seed_snapshot.json"))
    # 后端写路径不在 allowlist。
    check("deny-handler-path", not _is_allowed_path("zw_brain/command/handlers/j1/request.py"))

    if failures:
        print(f"[no-hardcoded-org-literal --self-test] FAIL: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("[no-hardcoded-org-literal --self-test] OK: 10 self-test assertions passed.")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    return _run_repo()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
