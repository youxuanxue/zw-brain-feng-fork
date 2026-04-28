#!/usr/bin/env bash
# Create dev-rules/ as a symlink to the canonical local mirror (方案 A).
# Usage: bash scripts/link-dev-rules.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ]; then
  echo "FAIL: not inside a git repository"
  exit 1
fi

CANON="${DEV_RULES_HOME:-$HOME/Codes/dev-rules}"
if [ ! -d "$CANON/.git" ]; then
  echo "FAIL: canonical dev-rules not found at $CANON"
  echo "  Obtain a git clone of your dev-rules mirror at that path (or set DEV_RULES_HOME)."
  exit 1
fi

TARGET="$ROOT/dev-rules"
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
  echo "FAIL: $TARGET exists and is not a symlink (remove or move it first)"
  exit 1
fi

ln -sfn "$CANON" "$TARGET"
echo "ok: $TARGET -> $CANON"
