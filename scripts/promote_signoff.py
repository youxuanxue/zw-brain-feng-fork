#!/usr/bin/env python3
"""R13 业务方签字流量 — PR label → .feature Status 自动升级.

zw-brain 飞轮反模式 #2（docs/approved/zw-brain-flywheel.md §九）：
  业务方 review 不签字 / 不批量签字 → 30 Draft 永远不 Verified → R13 通道阻塞.

本脚本走通 R13 通道：
  - 输入：PR comment label `business-signoff:<scope>` 或 `business-signoff:<feature-name>`
  - 动作：扫 .testing/**/*.feature，把对应 scope/feature 的 Status: Draft|InTest → Ready
  - 验证：preflight 段 37 三角守卫保证字段一致

scope 支持：
  - `business-signoff: wave-0`     — 升级 Wave 0 全部 InTest feature
  - `business-signoff: wave-1`     — 同
  - `business-signoff: e1.F2`      — 升级 Twin-F = e1.F2 的 feature
  - `business-signoff: j1-objection-use`  — 升级单个 feature（按文件名）
  - `business-signoff: legacy-not-reproduce`  — 单独：升级 docs/legacy-not-reproduce-signoff.md status

使用：
    # 干跑（看会改哪些 feature）
    ./scripts/promote_signoff.py --pr 123 --dry-run

    # 真改（commit message + 写文件）
    ./scripts/promote_signoff.py --pr 123

    # 不连 GitHub，本地指定 scope
    ./scripts/promote_signoff.py --scope wave-0 --to Ready

GitHub PR label 触发可由 workflow 自动接入（本 PR 仅落地脚本；workflow 后续接力）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTING_DIR = REPO / ".testing"
SIGNOFF_DOC = REPO / "docs" / "legacy-not-reproduce-signoff.md"

STATUS_RE = re.compile(r"^(# Status:\s*)(\S+)\s*$", re.MULTILINE)
WAVE_DIR_RE = re.compile(r"wave-([0-4])")
TWIN_F_RE = re.compile(r"^# Twin-F:\s*(\S+)", re.MULTILINE)
WAVE_HEADER_RE = re.compile(r"^# Wave:\s*(\S+)", re.MULTILINE)

VALID_TRANSITIONS = {
    "Draft": ["Ready"],
    "InTest": ["Ready"],
    "Ready": ["Verified"],
}


def _gh_pr_labels(pr_num: int) -> list[str]:
    """获取 PR labels（依赖 gh CLI 在 PATH）"""
    try:
        out = subprocess.run(
            ["gh", "pr", "view", str(pr_num), "--json", "labels"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode != 0:
            return []
        data = json.loads(out.stdout or "{}")
        return [label["name"] for label in data.get("labels", []) if "name" in label]
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []


def _extract_signoff_scopes(labels: list[str]) -> list[str]:
    """从 PR labels 抽取 business-signoff:<scope>"""
    prefix = "business-signoff:"
    return [lbl[len(prefix):].strip() for lbl in labels if lbl.startswith(prefix)]


def _feature_matches_scope(feature_path: Path, scope: str, content: str) -> bool:
    """判定 .feature 是否被 scope 命中"""
    # scope 是 wave-N
    if scope.startswith("wave-"):
        return scope in feature_path.as_posix()
    # scope 是 eN.FX
    if re.match(r"^e[1-6]\.F\d+$", scope):
        twin_f_match = TWIN_F_RE.search(content)
        if twin_f_match:
            return scope in twin_f_match.group(1)
        return False
    # scope 是整 epic eN（D36：效果验收常按 epic 整批签）——命中该 epic 全部 .feature
    if re.match(r"^e[1-6]$", scope):
        twin_f_match = TWIN_F_RE.search(content)
        if twin_f_match:
            return bool(re.match(rf"^{re.escape(scope)}\.F\d+", twin_f_match.group(1)))
        return False
    # scope 是 feature 文件名
    return feature_path.stem == scope


def _bump_status(content: str, target: str, dry_run: bool) -> tuple[str, str | None]:
    """升级 .feature header Status；返回 (新 content, 原 status) 或 (content, None) 若不升级"""
    m = STATUS_RE.search(content)
    if not m:
        return content, None
    current = m.group(2)
    if current == target:
        return content, None
    if current not in VALID_TRANSITIONS or target not in VALID_TRANSITIONS[current]:
        return content, None
    if dry_run:
        return content, current
    new_content = STATUS_RE.sub(f"{m.group(1)}{target}", content, count=1)
    return new_content, current


def _bump_signoff_doc(target: str, dry_run: bool) -> bool:
    """升级 docs/legacy-not-reproduce-signoff.md status: awaiting-signoff → approved"""
    if not SIGNOFF_DOC.is_file():
        return False
    text = SIGNOFF_DOC.read_text(encoding="utf-8")
    if "status: awaiting-signoff" not in text:
        return False
    if target != "approved":
        return False
    if dry_run:
        return True
    new_text = text.replace("status: awaiting-signoff", "status: approved", 1)
    SIGNOFF_DOC.write_text(new_text, encoding="utf-8")
    return True


def _process_scope(scope: str, target: str, dry_run: bool) -> list[tuple[Path, str]]:
    """处理一个 scope；返回 [(path, 原 status), ...]"""
    changes: list[tuple[Path, str]] = []

    # 特殊 scope: legacy-not-reproduce
    if scope == "legacy-not-reproduce":
        if _bump_signoff_doc("approved", dry_run):
            changes.append((SIGNOFF_DOC, "awaiting-signoff"))
        return changes

    for fp in TESTING_DIR.rglob("*.feature"):
        try:
            content = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _feature_matches_scope(fp, scope, content):
            continue
        new_content, prev = _bump_status(content, target, dry_run)
        if prev is not None:
            if not dry_run:
                fp.write_text(new_content, encoding="utf-8")
            changes.append((fp, prev))
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="R13 业务方签字流量 — PR label → Status 升级")
    parser.add_argument("--pr", type=int, help="PR 号；从 gh CLI 拉 labels")
    parser.add_argument("--scope", help="本地指定 scope（覆盖 --pr label 抽取）")
    parser.add_argument(
        "--to",
        default="Ready",
        choices=["Ready", "Verified"],
        help="目标 Status（默认 Ready；Verified 用于客户上线后回灌）",
    )
    parser.add_argument("--dry-run", action="store_true", help="不写文件，仅显示 diff")
    args = parser.parse_args()

    scopes: list[str] = []
    if args.scope:
        scopes = [args.scope]
    elif args.pr:
        labels = _gh_pr_labels(args.pr)
        scopes = _extract_signoff_scopes(labels)
        if not scopes:
            print(f"[promote-signoff] PR #{args.pr} 无 business-signoff:* label")
            return 0
    else:
        parser.error("需 --pr 或 --scope")
        return 2

    total = 0
    for scope in scopes:
        changes = _process_scope(scope, args.to, args.dry_run)
        prefix = "[dry-run]" if args.dry_run else "[promote]"
        if not changes:
            print(f"{prefix} scope='{scope}' → 无 feature 升级（可能已是目标 status）")
            continue
        print(f"{prefix} scope='{scope}' → {args.to}: {len(changes)} change(s)")
        for path, prev in changes:
            rel = path.relative_to(REPO).as_posix()
            print(f"  {rel}: {prev} → {args.to}")
        total += len(changes)

    if args.dry_run:
        print(f"\n[dry-run] would change {total} file(s) total. Re-run without --dry-run to apply.")
    else:
        print(f"\n[promote-signoff] OK: {total} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
