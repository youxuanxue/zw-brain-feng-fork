#!/usr/bin/env python3
"""check_external_register_metadata.py — preflight 段 30（D68 T1）

外部第三方 Agent 经 ``source_type=external-register`` 注册时，Registry manifest 强制 4 字段
（runtime_spec_version / agent_yaml_ref / agent_trust_level / workspace_required）；**其它**
source_type 一律**禁止**出现这 4 字段（防字段污染 / 防 embedded 路径误带）。

判定（扫 zw_brain/capability_registry/registered/*.json）：
  - source_type == 'external-register' → 必须含 4 字段且取值合法（委派 validate_manifest）。
  - 其它（含 absent / builtin）→ 4 字段必须全部缺席。

退出码：0 通过 / 1 违规。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from zw_brain.capability_registry.runtime import (  # noqa: E402
    EXTERNAL_REGISTER_REQUIRED_FIELDS,
    validate_manifest,
)

REGISTRY_DIR = REPO / "zw_brain" / "capability_registry" / "registered"


def scan() -> list[str]:
    violations: list[str] = []
    for path in sorted(REGISTRY_DIR.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            violations.append(f"{path.name}: unreadable ({exc})")
            continue
        if not isinstance(manifest, dict):
            continue
        slug = manifest.get("slug", path.stem)
        is_external = manifest.get("source_type") == "external-register"
        present = [f for f in EXTERNAL_REGISTER_REQUIRED_FIELDS if f in manifest]
        if is_external:
            try:
                validate_manifest(manifest)  # 含 4 字段强制 + 取值校验
            except ValueError as exc:
                violations.append(f"{slug}: external-register invalid — {exc}")
        elif present:
            violations.append(
                f"{slug}: source_type={manifest.get('source_type')!r} 不得带 external-register 专属字段 "
                f"{present}（防字段污染 — 仅 external-register 可有）"
            )
    return violations


def main() -> int:
    if not REGISTRY_DIR.is_dir():
        print(f"[external-register-metadata] skip: {REGISTRY_DIR} not present")
        return 0
    violations = scan()
    total = len(list(REGISTRY_DIR.glob("*.json")))
    if violations:
        print(f"[external-register-metadata] FAIL: {len(violations)} 处违规（扫 {total} manifest）：")
        for v in violations:
            print(f"  - {v}")
        print("[external-register-metadata] hint: D68 T1——external-register 须含 4 字段且合法；")
        print("[external-register-metadata]       非 external-register 禁带这 4 字段（防污染）。见 docs/agent-runtime-t1-readiness.md §5。")
        return 1
    print(f"[external-register-metadata] ok: {total} manifest 合规（external-register 4 字段强制 / 其它无污染）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
