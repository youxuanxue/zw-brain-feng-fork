#!/usr/bin/env python3
"""check_permission_roles_subset.py — preflight 段 26（R-005 交叉守卫）.

不变量：``policy.PERMISSION_ROLES`` 的每个权限 key 都必须被**至少一个** capability
manifest 的 ``permissions`` 字段声明——即 ``PERMISSION_ROLES.keys() ⊆
⋃ manifest.permissions``。

为什么：PERMISSION_ROLES 是「权限 → 允许角色集合」的授权矩阵；某 key 若没有任何
manifest 声明它，则这条授权规则永远不会被 ``enforce_manifest_policy`` 命中——
**机制空转的死权限门**。R-005 实证：``catalog.lead_dept_topic_review/revoke.execute``
两条随 D55 专题包整面下线后零 manifest 声明、交集恒空，是 211 key 中仅有的孤儿。
本守卫把「死权限门回潮」结构性钉死：新增 PERMISSION_ROLES 条目却无对应 manifest
权限声明，即 FAIL（当前孤儿门禁 = 0）。

退出码：0 = 孤儿数为 0；1 = 存在孤儿权限 key。
接入：scripts/preflight.sh 段 26。
"""
from __future__ import annotations

import json
import sys

from guard_lib import iter_files, repo_root

REPO = repo_root()
REGISTERED_DIR = "zw_brain/capability_registry/registered"


def _declared_permissions() -> set[str]:
    declared: set[str] = set()
    for path in iter_files(extensions=(".json",), roots=(REGISTERED_DIR,)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for perm in data.get("permissions") or []:
            declared.add(str(perm))
    return declared


def main() -> int:
    sys.path.insert(0, str(REPO))
    from zw_brain.domain.policy import PERMISSION_ROLES  # noqa: PLC0415

    declared = _declared_permissions()
    orphans = sorted(set(PERMISSION_ROLES) - declared)

    if orphans:
        print(
            f"[permission-roles-subset] FAIL: {len(orphans)} 个 PERMISSION_ROLES key 无任何"
            f" manifest 声明（死权限门、机制空转）：",
            file=sys.stderr,
        )
        for o in orphans:
            print(f"  ORPHAN: {o}", file=sys.stderr)
        print(
            "\nfix（承 R-005）：删除该死 PERMISSION_ROLES 条目，或为对应 capability manifest"
            "\n补 permissions 声明使授权规则真正生效——授权矩阵不得有永不命中的空转条目。",
            file=sys.stderr,
        )
        return 1

    print(
        f"[permission-roles-subset] OK: PERMISSION_ROLES {len(PERMISSION_ROLES)} keys"
        f" ⊆ manifest 权限并集（declared={len(declared)}），无死权限门"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
