#!/usr/bin/env python3
"""check_iam_prod_guard.py — preflight 段 23（G1.4）

强约束（机械门禁，对应 docs/preflight-debt.md 的「dev-iam-bypass」debt
升级 trigger 触发）：

    任何被识别为「生产部署清单」的文件（Dockerfile* / docker-compose*.yaml /
    scripts/deploy*.sh）一旦同时出现：
        - ZW_BRAIN_DEPLOY_MODE=prod  （声明这是生产入口）
        - 任意 ZW_BRAIN_DEV_IAM_BYPASS / ZW_BRAIN_DEV_IAM_BYPASS_ACK 字面值
    即视为「dev IAM bypass 漏到生产部署」，preflight 必须红灯。

为什么 G1 期落地：
    - debt entry trigger 是「首个真实客户部署上线前」——G3 标尺正是「找一个
      真客户在屏幕前 30 分钟跑通」，等价于这个 trigger。
    - dev-iam-bypass 在 prod 等于关掉身份认证；客户机房若误开为零认证后果不可逆。
    - 软提醒已被证明不够，必须升级为「commit-time 拦截」。

设计原则：
    - 只扫部署清单（不扫 tests/ / docs/ / .data/ / .testing/ ——这些是 OK 的）
    - 检查 ZW_BRAIN_DEPLOY_MODE 是否声明为 prod（不区分大小写）；不声明 prod
      则跳过此文件
    - 若声明 prod 且同文件出现 dev-iam-bypass 任一关键字 → 红灯
    - **不**检查环境变量运行时取值（运行时由代码层 startup hook 守护）

退出码：
    0 = 全部通过
    1 = 至少一个 prod 部署文件出现 dev-iam-bypass 关键字

使用：
    ./scripts/check_iam_prod_guard.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 部署清单路径（glob 模式，相对 REPO）
DEPLOY_MANIFEST_GLOBS: tuple[str, ...] = (
    "Dockerfile",
    "Dockerfile_*",
    "Dockerfile.*",
    "docker-compose*.yaml",
    "docker-compose*.yml",
    "scripts/deploy*.sh",
    "scripts/deploy_*.sh",
    "scripts/deploy-*.sh",
)

# 排除项：deploy_dev*.sh 命中 DEPLOY_MANIFEST_GLOBS 但属于 dev 部署，需排除。
# 注：start-local.sh / customer_demo_5min.sh 本就不在扫描集（DEPLOY_MANIFEST_GLOBS
# 只 match deploy*.sh），不必再 exclude。
EXCLUDE_GLOBS: tuple[str, ...] = (
    "scripts/deploy_dev*.sh",
)

DEV_BYPASS_KEYS: tuple[str, ...] = (
    "ZW_BRAIN_DEV_IAM_BYPASS",
    "ZW_BRAIN_DEV_IAM_BYPASS_ACK",
)

PROD_MODE_PATTERN = re.compile(r"ZW_BRAIN_DEPLOY_MODE\s*[=:]\s*['\"]?prod['\"]?", re.IGNORECASE)


def gather_manifests() -> list[Path]:
    found: set[Path] = set()
    for pattern in DEPLOY_MANIFEST_GLOBS:
        for match in REPO.glob(pattern):
            if not match.is_file():
                continue
            rel = match.relative_to(REPO).as_posix()
            if any(match.match(excl) or rel == excl for excl in EXCLUDE_GLOBS):
                continue
            found.add(match)
    return sorted(found)


def detect_violations(manifest: Path) -> list[str]:
    """Return list of violation lines (1-indexed display); empty if clean."""
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return []
    if not PROD_MODE_PATTERN.search(text):
        # 文件未声明 prod，不扫描
        return []
    violations: list[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        # 跳过 comment 行（'#' 起头）
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for key in DEV_BYPASS_KEYS:
            if key in line:
                violations.append(f"line {idx}: {line.strip()}")
                break
    return violations


def main() -> int:
    manifests = gather_manifests()
    total_violations = 0
    failed_files: list[tuple[Path, list[str]]] = []
    for manifest in manifests:
        violations = detect_violations(manifest)
        if violations:
            failed_files.append((manifest, violations))
            total_violations += len(violations)

    if failed_files:
        print(
            f"[iam-prod-guard] FAIL: {total_violations} dev-iam-bypass leak(s) "
            f"in {len(failed_files)} prod deploy manifest(s)",
            file=sys.stderr,
        )
        for manifest, violations in failed_files:
            rel = manifest.relative_to(REPO).as_posix()
            print(f"  {rel}:", file=sys.stderr)
            for v in violations:
                print(f"    {v}", file=sys.stderr)
        print(
            "  fix: remove ZW_BRAIN_DEV_IAM_BYPASS* lines from prod manifests; "
            "dev bypass is only for scripts/start-local.sh + scripts/customer_demo_5min.sh.",
            file=sys.stderr,
        )
        return 1
    print(
        f"[iam-prod-guard] ok: scanned {len(manifests)} prod deploy manifest(s), 0 dev-iam-bypass leaks"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
