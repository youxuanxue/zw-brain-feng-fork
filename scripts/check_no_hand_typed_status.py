#!/usr/bin/env python3
"""check_no_hand_typed_status.py — preflight 段 62（反向守卫，替原段 58）.

单一事实源不变量：status 不再被存储/手敲——它是 `gen_feature_status.py` 从
SPEC+MEASUREMENT+SIGN-OFF 现算的派生视图。故 `.feature` 里**禁止**再出现手写的
`# Status:` 或任何状态词。命中即 FAIL（锁死"不可复存"，让漂移结构性消失）。

排期外意图用 spec 自有的 `# Deferred: <理由/ref>` 表达（非 status，本守卫放行）。
本守卫严格限 `.feature` header 行，绝不碰 `.testing/README.md` / flywheel.md 的说明 prose。

Exit：0 = 干净；1 = 有残留
Usage: ./scripts/check_no_hand_typed_status.py [--verbose]
接入：scripts/preflight.sh 段 62
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_status_lib import REPO, TESTING_DIR, all_features  # noqa: E402

STATUS_LINE = re.compile(r"^#\s*Status\s*:", re.IGNORECASE)
# 旧状态词若以裸 header 形式回潮也拦（如 `# Verified:` / `# Done:`）
STATUS_WORD_LINE = re.compile(r"^#\s*(Verified|Done|Accepted|Completed|Ready|InTest|Draft|Backlog)\s*:", re.IGNORECASE)


def main() -> int:
    ap = argparse.ArgumentParser(description="禁手写 feature status（段 62）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not TESTING_DIR.is_dir():
        print("[no-hand-typed-status] skip: 无 .testing/")
        return 0

    violations: list[str] = []
    scanned = 0
    for fp in all_features():
        scanned += 1
        rel = fp.relative_to(REPO).as_posix()
        try:
            for n, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
                if n > 30:
                    break
                if STATUS_LINE.match(line) or STATUS_WORD_LINE.match(line):
                    violations.append(f"{rel}:{n}: {line.strip()}")
        except OSError as e:
            violations.append(f"{rel}: 读失败 {e}")

    if violations:
        print(f"[no-hand-typed-status] FAIL: scanned {scanned} .feature(s)，"
              f"{len(violations)} 处手写 status 残留：")
        for v in violations:
            print(f"  {v}")
        print("[no-hand-typed-status] status 现算不手写 —— 删该行；排期外用 `# Deferred:`；"
              "状态看 .testing/status/feature-status.md（gen_feature_status.py 生成）。")
        return 1

    print(f"[no-hand-typed-status] OK: scanned {scanned} .feature(s)，无手写 status（status 现算）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
