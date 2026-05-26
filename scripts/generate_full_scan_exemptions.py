#!/usr/bin/env python3
"""generate_full_scan_exemptions.py — preflight 段 32b

强约束（防止 read-path full-scan 豁免清单与代码不同步的机械门禁）：

    段 32 `check_read_path_full_scan.py` 允许带 `# full-scan-ok: <reason>` 注释的
    全表扫读路径放行；这是为了在不显著扩张 PR 范围的前提下保留旧点继续工作。
    但豁免不登记 → 隐性债务。本脚本：

    - 默认模式：扫 `zw_brain/` 下所有含 `# full-scan-ok:` 注释的文件，提取
      `file:line + reason + 周边上下文 ~2 行`，生成 `docs/full-scan-exemptions.md`
      （按文件分组的 markdown 列表）。
    - `--check` 模式：生成内容与 tracked 文件 diff，drift 则 FAIL（exit 1）；
      用于 preflight 段 32b 自动校验。

    生成的清单顶部注明 review 周期 = 每月一次，与 debt review 同步。

退出码：
    0 = (生成模式) 写入成功；(check 模式) 同步无漂移
    1 = (check 模式) 检测到 drift；diff hint 给出再生成命令

使用：
    ./scripts/generate_full_scan_exemptions.py           # 生成
    ./scripts/generate_full_scan_exemptions.py --check   # 校验同步
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SCAN_ROOT = REPO / "zw_brain"
DEFAULT_OUT = REPO / "docs" / "full-scan-exemptions.md"

# 匹配单行 `# full-scan-ok: <reason>` 注释（reason 至少 7 字符，与段 32 一致）
EXEMPTION_PATTERN = re.compile(r"#\s*full-scan-ok:\s*(.+)")


def scan(root: Path, base: Path | None = None) -> dict[str, list[tuple[int, str, list[str]]]]:
    """Return {relpath: [(line_no, reason, context_lines), ...]} sorted by line.

    `base` 用于计算 relative path；默认 = root.parent（即 root 的 parent 视为仓库根）。
    """
    if base is None:
        base = root.parent
    result: dict[str, list[tuple[int, str, list[str]]]] = {}
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        hits: list[tuple[int, str, list[str]]] = []
        for idx, line in enumerate(lines, 1):
            m = EXEMPTION_PATTERN.search(line)
            if not m:
                continue
            reason = m.group(1).strip()
            # 上下文：本行前 1 行 + 后 1 行（去掉空行）
            context_start = max(0, idx - 2)
            context_end = min(len(lines), idx + 1)
            ctx = [lines[i].rstrip() for i in range(context_start, context_end)]
            hits.append((idx, reason, ctx))
        if hits:
            try:
                rel = path.relative_to(base).as_posix()
            except ValueError:
                rel = path.as_posix()
            result[rel] = hits
    return result


def render(hits: dict[str, list[tuple[int, str, list[str]]]]) -> str:
    total = sum(len(v) for v in hits.values())
    lines: list[str] = []
    lines.append("# read-path full-scan 豁免清单")
    lines.append("")
    lines.append(
        "本清单由 `scripts/generate_full_scan_exemptions.py` 自动生成；不要手编辑。"
    )
    lines.append("")
    lines.append("**Review 周期**：每月一次（与 `docs/preflight-debt.md` debt review 同步——")
    lines.append("详见架构基线 §9.7.5）。每月把存活豁免逐条复核，问 3 个问题：")
    lines.append("")
    lines.append("1. trigger 条件是否已被现实触及（如多租户接入 / J1 量级进入万级）？")
    lines.append("2. PR 范围允许在本月把它修掉吗？")
    lines.append("3. 否则保留并把当月复核日期写进 reason 注释。")
    lines.append("")
    lines.append("**机械守卫**：段 32 `check_read_path_full_scan.py` 对**新增**全表扫一律拦下，")
    lines.append("必须显式加 `# full-scan-ok: <≥7 字符理由>` 才放行；段 32b 本脚本以 `--check`")
    lines.append("模式校验本清单与代码同步。")
    lines.append("")
    lines.append(f"当前豁免总数：**{total}** 条，分布在 {len(hits)} 个文件。")
    lines.append("")
    lines.append("---")
    lines.append("")
    for rel, items in sorted(hits.items()):
        lines.append(f"## `{rel}`")
        lines.append("")
        for line_no, reason, ctx in items:
            lines.append(f"### `{rel}:{line_no}`")
            lines.append("")
            lines.append(f"**Reason**: {reason}")
            lines.append("")
            lines.append("```python")
            lines.extend(ctx)
            lines.append("```")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=DEFAULT_SCAN_ROOT,
        help="扫描根目录（默认 zw_brain/）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="输出 markdown 路径（默认 docs/full-scan-exemptions.md）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="校验现有文件与生成内容一致；drift 则 exit 1",
    )
    args = parser.parse_args(argv)

    if not args.scan_root.is_dir():
        print(f"[full-scan-exemptions] skip: {args.scan_root} not present")
        return 0

    # 若 scan_root 在仓库内，relative_to(REPO)；否则用 scan_root.parent 作为 base
    base = REPO if args.scan_root.is_relative_to(REPO) else args.scan_root.parent
    hits = scan(args.scan_root, base=base)
    rendered = render(hits)

    if args.check:
        if not args.out.is_file():
            print(f"[full-scan-exemptions] FAIL: {args.out} 缺失；先跑 scripts/generate_full_scan_exemptions.py")
            return 1
        actual = args.out.read_text(encoding="utf-8")
        if actual != rendered:
            print(f"[full-scan-exemptions] FAIL: {args.out} 与代码不同步")
            print("  hint: 跑 scripts/generate_full_scan_exemptions.py 重新生成")
            return 1
        total = sum(len(v) for v in hits.values())
        print(
            f"[full-scan-exemptions] OK: {total} 豁免登记与代码同步（{len(hits)} 文件）"
        )
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    total = sum(len(v) for v in hits.values())
    print(
        f"[full-scan-exemptions] generated: {args.out} ({total} 豁免，{len(hits)} 文件)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
