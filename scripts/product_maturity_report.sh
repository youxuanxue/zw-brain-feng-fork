#!/usr/bin/env bash
# 产品成熟度周报（飞轮设计 §七.2）
# status 不再手写——从单一事实源现算（SPEC+MEASUREMENT+SIGN-OFF），见
# scripts/feature_status_lib.py / .testing/status/feature-status.md。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo "=== zw-brain 产品成熟度（$(date +%Y-%m-%d)）==="
"$PY" - <<'PYEOF'
import sys; sys.path.insert(0, "scripts")
import feature_status_lib as L
from collections import Counter
rows = L.compute_all()
c = Counter(r["status"] for r in rows)
total = len(rows)
order = ["Done", "Ready", "InTest", "Draft", "Backlog"]
for st in order:
    print(f"  {st}: {c.get(st, 0)}")
# 进度：Done=100% / Ready=50% / InTest=50%（绿但待签）/ 其余=0
score = c.get("Done", 0) * 100 + (c.get("Ready", 0) + c.get("InTest", 0)) * 50
pct = round(score / total) if total else 0
print(f"  ── 成熟度 {pct}%（Done 计 100，Ready/InTest 计 50；共 {total}）")
m = L.load_measurement()
sha = (m or {}).get("git_sha", "—")
print(f"  ── 测量基线 git_sha={sha[:12]}（陈旧请跑 scripts/capture_feature_status.py）")
print("  ── 明细见 .testing/status/feature-status.md（机械生成，勿手改）")
PYEOF
