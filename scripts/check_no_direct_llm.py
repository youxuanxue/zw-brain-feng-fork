#!/usr/bin/env python3
"""
check_no_direct_llm.py — preflight 段 10

强约束（设计基线 §十四 D6）：
    所有模型服务调用（LLM / Embedding / ASR / Rerank / OCR 等）必须走集团推理平台
    提供的统一 SDK / API；禁止任何模块直连 OpenAI / Anthropic / 百川 / 智谱 /
    通义等第三方 LLM API。

本脚本检查范围：
    1. 扫描项目内所有 .py 文件（除白名单目录外）
    2. 检查 import 黑名单 SDK
    3. 检查源码中黑名单 API host 字符串

唯一允许的 LLM 出口：
    zw_brain.shared.inference.client（D14 Phase 0 mock 实现，文档到位后只换内部）

退出码：0 = 全部通过；1 = 至少一处违反

使用：
    ./scripts/check_no_direct_llm.py
    ./scripts/check_no_direct_llm.py --verbose

接入：scripts/preflight.sh 段 10
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── 黑名单：禁止 import 的第三方 LLM SDK 顶层包名 ───────────────────────
# 命中即 fail（除非在白名单目录中，例如 dev-rules/）
BLACKLIST_IMPORTS = {
    "openai",
    "anthropic",
    "google.generativeai",
    "vertexai",
    "cohere",
    "mistralai",
    "baichuan_sdk",  # 百川官方 SDK 包名
    "zhipuai",  # 智谱 GLM SDK
    "dashscope",  # 阿里通义千问 SDK
    "qianfan",  # 百度千帆 SDK
    "doubao",  # 字节豆包
    "moonshot",  # Kimi
    "deepseek",  # DeepSeek 官方 SDK（如有）
}

# ── 黑名单：禁止出现在源码中的第三方 LLM API host ────────────────────────
BLACKLIST_HOSTS = {
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.cohere.ai",
    "api.mistral.ai",
    "api.baichuan-ai.com",
    "open.bigmodel.cn",  # 智谱
    "dashscope.aliyuncs.com",  # 通义
    "qianfan.baidubce.com",  # 千帆
    "ark.cn-beijing.volces.com",  # 豆包
    "api.moonshot.cn",
    "api.deepseek.com",
}

# ── 白名单：以下目录/文件不扫描（外部依赖、文档示例、本检查脚本本身）────
WHITELIST_DIRS = {
    ".git",
    "dev-rules",  # 子模块，独立审计
    "old",  # 旧平台素材（含 old/integrated-bigdata-platform 旧 README + 截图），已 .gitignore
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".testing/fixtures",  # fixture 数据可能含示例 URL（业务数据）
    "scripts",  # 本检查脚本自身就含黑名单字面量；豁免 scripts/check_*.py（按文件名进一步过滤）
}

# ── 白名单：唯一合法的 LLM 出口模块（D14 → D6 内部实现）────────────────
ALLOWED_LLM_GATEWAY = "zw_brain.shared.inference.client"

# ── 守卫面注册（供元守卫 check_guard_scan_surface 对账）─────────────────
# D6 守卫扫主源码 + 前端 + scripts/tests/.testing（R-003 后含 zw-brain-web/src）。
# 声明的 extensions 是「会承载第三方 LLM SDK import / host 的源码扩展名」全集。
_D6_TARGET_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".json", ".yaml", ".yml", ".md")
try:
    from guard_lib import register_grep_guard

    register_grep_guard(
        "no-direct-llm",
        roots=("zw_brain", "scripts", "tests", ".testing", "zw-brain-web/src"),
        extensions=_D6_TARGET_EXTENSIONS,
        note="D6 模型调用收口集团推理平台",
    )
except ImportError:
    pass

# ── 白名单：反向定义"禁止 host"的防御性代码（D6 校验器自身）────────────
# 这些文件持有 BLACKLIST 字面量是用于拒绝 AGENT.yaml manifest 引用第三方 LLM，
# 不是真实调用。豁免它们以避免反向引用被误判为违规。
WHITELIST_FILES = {
    "zw_brain/shared/agent_runtime/manifest_checks.py",
}


def should_skip(path: Path, repo_root: Path) -> bool:
    """是否跳过该路径（命中白名单目录/文件或非 .py 文件）。"""
    rel = path.relative_to(repo_root)
    if str(rel) in WHITELIST_FILES:
        return True
    parts = rel.parts
    # 白名单目录 prefix 匹配
    for wd in WHITELIST_DIRS:
        wd_parts = wd.split("/")
        if len(parts) >= len(wd_parts) and list(parts[: len(wd_parts)]) == wd_parts:
            # scripts/ 下唯一豁免的是 check_*.py（自身扫描会误报）
            if wd == "scripts":
                # 若是 scripts/check_*.py，跳过
                if rel.name.startswith("check_") and rel.name.endswith(".py"):
                    return True
                # 其他 scripts/ 下脚本（如 export_agent_contract.py）正常扫描
                return False
            return True
    return False


def scan_file(path: Path, repo_root: Path) -> list[tuple[int, str, str]]:
    """扫描单个文件，返回 [(line_no, kind, snippet), ...]。"""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # 跳过注释行（行首 # 或 // 或 /*）— 但保留 docstring 内的扫描（防止字符串里藏 host）
        is_comment = stripped.startswith("#") or stripped.startswith("//")

        # 1) import 检查（仅 .py 文件，且非注释）
        if path.suffix == ".py" and not is_comment:
            m = re.match(
                r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
                line,
            )
            if m:
                module = m.group(1)
                top_pkg = module.split(".")[0]
                # 检查完整路径或顶层包是否命中黑名单
                if module in BLACKLIST_IMPORTS or top_pkg in BLACKLIST_IMPORTS:
                    violations.append(
                        (lineno, "BLACKLIST_IMPORT", line.rstrip())
                    )

        # 2) host 字面量检查（任何文本文件，含注释也查 — 防止有人把 URL 注释里残留）
        for host in BLACKLIST_HOSTS:
            if host in line:
                violations.append((lineno, "BLACKLIST_HOST", line.rstrip()))
                break

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--root",
        default=None,
        help="repo root (default: auto-detect via git or relative)",
    )
    args = parser.parse_args()

    if args.root:
        repo_root = Path(args.root).resolve()
    else:
        # 自动定位 repo root（脚本位于 scripts/ 下）
        repo_root = Path(__file__).resolve().parent.parent

    if args.verbose:
        print(f"[no-direct-llm] scanning under: {repo_root}")

    # 优先扫描 zw_brain/ 主源码目录，其次扫描其余 .py / .ts / .js
    target_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".json", ".yaml", ".yml", ".md"}

    # zw_brain/ 是设计基线 §4.4.5 工程布局的主源码根
    main_src = repo_root / "zw_brain"
    if not main_src.exists():
        # zw_brain/ 还没建（Phase 0 早期），把扫描范围降级为「仅项目级 scripts + tests」
        scan_roots = [
            d for d in (
                repo_root / "scripts",
                repo_root / "tests",
                repo_root / ".testing",
            )
            if d.exists()
        ]
        if not scan_roots:
            print("[no-direct-llm] skip: zw_brain/ not yet created and no scripts/tests to scan")
            print("  (this check will become enforcing once Phase 1 introduces zw_brain/ source)")
            return 0
        if args.verbose:
            print(f"[no-direct-llm] zw_brain/ not present; scanning fallback roots: {[str(r) for r in scan_roots]}")
    else:
        scan_roots = [main_src]
        # 同时也扫描 scripts/ 和 tests/（如果存在）
        # R-003：前端 zw-brain-web/src 也是 D6 守卫面——.vue/.ts 已在 target_extensions、
        # node_modules 已在 WHITELIST_DIRS；前端直连第三方 LLM SDK / host 同样违 D6
        # （5 消费面共享同一推理出口口径）。
        for extra in (
            repo_root / "scripts",
            repo_root / "tests",
            repo_root / ".testing",
            repo_root / "zw-brain-web" / "src",
        ):
            if extra.exists():
                scan_roots.append(extra)

    total_files = 0
    total_violations = 0
    files_with_violations = 0

    for root in scan_roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in target_extensions:
                continue
            if should_skip(path, repo_root):
                continue
            total_files += 1
            violations = scan_file(path, repo_root)
            if violations:
                files_with_violations += 1
                total_violations += len(violations)
                rel = path.relative_to(repo_root)
                print(f"\n  ✗ {rel}")
                for lineno, kind, snippet in violations:
                    print(f"      L{lineno} [{kind}] {snippet[:120]}")

    print()
    if total_violations == 0:
        print(f"[no-direct-llm] OK: scanned {total_files} files, no third-party LLM SDK / host detected")
        print(f"  (allowed gateway: {ALLOWED_LLM_GATEWAY})")
        return 0
    else:
        print(f"[no-direct-llm] FAIL: {total_violations} violation(s) across {files_with_violations} file(s)")
        print(f"  policy (D6): all model calls MUST go through {ALLOWED_LLM_GATEWAY}")
        print("  fix: replace direct SDK / API host usage with the unified inference client")
        return 1


if __name__ == "__main__":
    sys.exit(main())
