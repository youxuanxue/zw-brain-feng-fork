#!/usr/bin/env python3
"""check_signoff_package.py — preflight 段 53

业务方 sign-off 材料包（`docs/**/*business-review-package*.md`）的三层质量守卫。
由 D35 确立——把本会话「上帝视角 Jobs」手抓的三类问题硬化为机械检查：

  Layer 1 数据真实性：判定表里标「seed 真实 / dump 命中 / dump 未命中」的行，
      必须真的在 zw_brain/domain/seed_snapshot.json / old/10示例数据 dump 命中，
      否则 FAIL（捕获"声称真实却查无此目录"——本会话手抓的医保码/异地就医误标、
      catalog_code 漂移就属此类）。dump 缺位（CI）→ 显式 skip，不 `|| true` 静默吞错（D22）。
  Layer 2 完整性：禁过程/估算数字（N 分钟 / N-M 天 / worker·day / 未 stat-wrap 的 N 态）；
      强制「启动硬前置」节存在；每个含「业务方判定」列的表必须配「建议」列。
  Layer 3 概念边界（WARN）：触及 legacy 概念（共享专区/专题包/主题库/示范应用/数购车）
      但全文无「边界」澄清节 → 告警。

Exit：0 = OK（含纯 WARN）；1 = FAIL。

Usage:
    ./scripts/check_signoff_package.py                       # 扫全部材料包
    ./scripts/check_signoff_package.py <path.md> [<path2>]   # 指定文件
    ./scripts/check_signoff_package.py --verbose

接入：scripts/preflight.sh 段 53
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from signoff_lib import BANNED_NUMBER_PATTERNS, parse_tables

REPO = Path(__file__).resolve().parent.parent
SEED_JSON = REPO / "zw_brain" / "domain" / "seed_snapshot.json"
DUMP_GLOB = "old/10示例数据/dump-dsp_catalog-*.sql"

LEGACY_TERMS = ["共享专区", "专题包", "主题库", "示范应用", "数购车"]

CJK = r"一-鿿"


def _strip_parens(text: str) -> str:
    """去掉中英文括号内补充说明，保留主体名。"""
    text = re.sub(r"（[^（）]*）", "", text)
    text = re.sub(r"\([^()]*\)", "", text)
    return text.strip()


def _candidates(first_cell: str) -> list[str]:
    """从行首单元格抽取查找候选键：反引号 token + 长编码 + ≥4 字 CJK 片段 + 整名。"""
    cands: list[str] = []
    cands += re.findall(r"`([^`]+)`", first_cell)                      # 反引号 code/URN
    cands += re.findall(r"[0-9A-Za-z][0-9A-Za-z./]{7,}", first_cell)   # 长编码（owner/URN 裸写）
    title = _strip_parens(re.sub(r"`[^`]*`", "", first_cell))
    title = re.sub(r"[*_>#]", "", title).strip()
    if title:
        cands.append(title)
    # 按非 CJK 分隔切，取 ≥4 字的 CJK 片段（鲁棒于标点差异）
    for run in re.split(rf"[^{CJK}]+", title):
        if len(run) >= 4:
            cands.append(run)
    # 去重保序
    seen, out = set(), []
    for c in cands:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _classify(reality_cell: str) -> str:
    """按优先级判定真实性标签类别。注意 '待入 seed' 与 'dump 命中' 共存时归 DUMP。"""
    c = reality_cell
    if "未命中" in c:
        return "UNHIT"
    if "命中" in c or "dump" in c.lower():
        return "DUMP"
    if "真实" in c and "seed" in c:
        return "SEED_STRICT"
    if "seed" in c:
        return "SEED_SOFT"
    return "SKIP"


def _load(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def check_doc(path: Path, seed_text: str, dump_text: str | None, verbose: bool) -> tuple[list[str], list[str]]:
    """返回 (fails, warns)。"""
    fails: list[str] = []
    warns: list[str] = []
    text = _load(path)
    rel = path.relative_to(REPO)

    # ---- Layer 2: 强制节 ----
    if not re.search(r"启动硬前置|sequencing", text):
        fails.append(f"{rel}: 缺「启动硬前置（sequencing）」强制节（无上游依赖也须显式写『无』）")

    # ---- Layer 2: 禁过程数字 ----
    for pat, desc in BANNED_NUMBER_PATTERNS:
        for m in pat.finditer(text):
            ln = text[: m.start()].count("\n") + 1
            fails.append(f"{rel}:{ln}: 禁用{desc} → 「{m.group(0).strip()}」（删除或改为 stat 块/定性描述）")

    tables = parse_tables(text)

    # ---- Layer 2: 判定表必须有「建议」列 ----
    for t in tables:
        hdr = "".join(t["header"])
        if "业务方判定" in hdr and "建议" not in hdr:
            fails.append(f"{rel}: 含「业务方判定」的表缺「建议」列 → 业务方无法快签（表头：{' | '.join(t['header'])}）")

    # ---- Layer 1: 数据真实性 ----
    for t in tables:
        # 找「数据真实性」列与行首列
        try:
            ri = next(i for i, h in enumerate(t["header"]) if "真实" in h or "数据真实" in h)
        except StopIteration:
            continue
        sugg_i = next((i for i, h in enumerate(t["header"]) if "建议" in h), None)
        for row in t["rows"]:
            if len(row) <= ri:
                continue
            reality = row[ri]
            cls = _classify(reality)
            if cls == "SKIP":
                continue
            subject = row[0] if row else ""
            cands = _candidates(subject)
            sugg = row[sugg_i] if (sugg_i is not None and len(row) > sugg_i) else ""

            if cls == "UNHIT":
                if "排除" not in sugg and not re.search(r"数据源|来源", reality + sugg):
                    fails.append(f"{rel}: 「{_strip_parens(subject)[:24]}」标 dump 未命中，但建议非『排除』且未指明数据源（D11 禁 Mock）")
                continue

            if cls == "DUMP":
                if dump_text is None:
                    if verbose:
                        warns.append(f"{rel}: dump 不在工作区，skip 「{_strip_parens(subject)[:24]}」的 dump 命中校验")
                    continue
                if not any(c in dump_text for c in cands):
                    fails.append(f"{rel}: 「{_strip_parens(subject)[:24]}」标 dump 命中，但 {DUMP_GLOB} 查无（候选 {cands[:3]}）")
                continue

            # SEED_STRICT / SEED_SOFT
            hit = any(c in seed_text for c in cands)
            if not hit:
                msg = f"{rel}: 「{_strip_parens(subject)[:24]}」标 seed 真实，但 seed_snapshot.json 查无（候选 {cands[:3]}）"
                if cls == "SEED_STRICT":
                    fails.append(msg)
                else:
                    warns.append(msg + "（soft：asset/subscriber 类，确认命名）")

    # ---- Layer 3: 概念边界 WARN ----
    if any(term in text for term in LEGACY_TERMS) and "边界" not in text:
        warns.append(f"{rel}: 触及 legacy 概念但无『边界』澄清节（防概念漂移，D34.a）")

    return fails, warns


def discover() -> list[Path]:
    out = []
    for p in REPO.glob("docs/**/*business-review-package*.md"):
        if "templates" in p.parts:
            continue  # 模板含禁词示例，豁免
        out.append(p)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="业务方 sign-off 材料包三层守卫（D35 / 段 53）")
    ap.add_argument("paths", nargs="*", help="指定文件；缺省扫 docs/**/*business-review-package*.md")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    targets = [Path(p).resolve() for p in args.paths] if args.paths else discover()
    if not targets:
        print("[signoff-package] OK: 无 sign-off 材料包待检")
        return 0

    seed_text = _load(SEED_JSON)
    if not seed_text:
        print(f"[signoff-package] FAIL: 读不到 {SEED_JSON.relative_to(REPO)}（Layer 1 失去真值源）")
        return 1
    dump_files = list(REPO.glob(DUMP_GLOB))
    dump_text = "".join(f.read_text(encoding="utf-8", errors="ignore") for f in dump_files) if dump_files else None

    all_fails, all_warns = [], []
    for t in targets:
        f, w = check_doc(t, seed_text, dump_text, args.verbose)
        all_fails += f
        all_warns += w

    for w in all_warns:
        print(f"  [WARN] {w}")
    if dump_text is None:
        print(f"  [skip] dump 不在工作区（{DUMP_GLOB}）→ Layer 1 dump 命中校验跳过（非静默：显式 skip）")

    if all_fails:
        print(f"[signoff-package] FAIL: {len(all_fails)} 项（扫 {len(targets)} 份材料包）：")
        for f in all_fails:
            print(f"  {f}")
        return 1
    print(f"[signoff-package] OK: {len(targets)} 份材料包通过（WARN {len(all_warns)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
