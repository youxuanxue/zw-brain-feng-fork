#!/usr/bin/env python3
"""Guard D68 cleanup: zw-brain runtime must not own inference SDK/env.

Standalone AgentRuntime is the only service that may hold model gateway
configuration. The zw-brain package must not import the retired inference
client or read the old ZW_BRAIN_INFERENCE_* variables.
"""

from __future__ import annotations

import sys
from pathlib import Path

NEEDLES = (
    "zw_brain.shared.inference",
    "ZW_BRAIN_INFERENCE_",
)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    root = repo / "zw_brain"
    violations: list[tuple[Path, int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".json", ".yaml", ".yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(needle in line for needle in NEEDLES):
                violations.append((path.relative_to(repo), lineno, line.strip()))

    if not violations:
        print("[no-zw-brain-inference-env] OK: zw_brain has no retired inference SDK/env references")
        return 0

    print("[no-zw-brain-inference-env] FAIL: zw-brain must not own inference SDK/env")
    for rel, lineno, line in violations:
        print(f"  {rel}:{lineno}: {line[:160]}")
    print("  fix: keep model gateway config in standalone AgentRuntime service side")
    return 1


if __name__ == "__main__":
    sys.exit(main())
