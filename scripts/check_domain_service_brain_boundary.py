#!/usr/bin/env python3
"""Preflight segment 49b — domain services must not grow BrainService back-channels.

The layer import guard (segment 49) prevents ``zw_brain/domain`` from runtime
importing ``zw_brain.command``. It does not catch the object-level inversion
introduced by the Action D transition: domain services still receive a
``BrainService`` instance and can call command/private state through
``self.brain.<attr>``.

This guard is a ratchet over the current transition debt:

- existing ``self.brain.<attr>`` accesses in ``zw_brain/domain/services`` are
  recorded as the baseline below;
- deleting or reducing those accesses is allowed;
- any new file, new attribute, or increased count fails preflight.

The desired end state is an empty baseline: domain services receive narrow
ports/repos instead of the command-layer god object.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "zw_brain" / "domain" / "services"

# Current transition baseline, measured as immediate ``self.brain.<attr>``
# accesses per file. Counts may shrink, but must not grow.
BASELINE: dict[str, dict[str, int]] = {
    "zw_brain/domain/services/application_service.py": {
        "_get_handler_deps": 3,
        "_legacy_mapping_refs": 2,
        "get_resource": 2,
    },
    "zw_brain/domain/services/catalog_service.py": {
        "_get_handler_deps": 2,
        "_legacy_mapping_refs": 4,
        "_mapping_diagnostics": 1,
        "_mapping_summary": 1,
        "_region_label": 1,
        "_reuse_gap_hint": 2,
        "_snapshot": 2,
        "_state_store": 2,
        "_topic_package_repo": 2,
        "get_resource": 2,
    },
    "zw_brain/domain/services/conditional_approval.py": {
        "_actor_for_role": 1,
        "_append_audit_feed": 3,
        "_auto_issue_credential_on_approval": 1,
        "_card_session": 1,
        "_mutate": 3,
    },
    "zw_brain/domain/services/delivery_service.py": {
        "_card_session": 2,
    },
    "zw_brain/domain/services/governance_service.py": {
        "_state_store": 2,
    },
    "zw_brain/domain/services/provider_service.py": {
        "_get_handler_deps": 1,
        "_mapping_diagnostics": 2,
        "_snapshot": 7,
        "_state_store": 8,
        "get_delivery_task": 2,
        "list_delivery_tasks": 1,
    },
    "zw_brain/domain/services/request_service.py": {
        "_actor_for_role": 1,
        "_append_audit_feed": 1,
        "_auto_issue_credential_on_approval": 1,
        "_card_session": 4,
        "_get_handler_deps": 3,
        "_mutate": 1,
        "_r2_review_evidence": 1,
        "_r2_review_reason": 1,
        "_state_store": 1,
        "get_request": 1,
    },
    "zw_brain/domain/services/topic_package_service.py": {
        "_get_handler_deps": 2,
        "_state_store": 2,
        "_topic_package_repo": 3,
    },
}


@dataclass(frozen=True)
class BrainAccess:
    attr: str
    line: int
    text: str


class BrainAccessVisitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.accesses: list[BrainAccess] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "brain"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "self"
        ):
            text = self.lines[node.lineno - 1].strip() if 0 < node.lineno <= len(self.lines) else ""
            self.accesses.append(BrainAccess(attr=node.attr, line=node.lineno, text=text))
        self.generic_visit(node)


def _scan_file(path: Path) -> list[BrainAccess]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    visitor = BrainAccessVisitor(text.splitlines())
    visitor.visit(tree)
    return visitor.accesses


def _current_accesses() -> dict[str, list[BrainAccess]]:
    current: dict[str, list[BrainAccess]] = {}
    if not SERVICES_DIR.exists():
        return current
    for path in sorted(SERVICES_DIR.glob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        accesses = _scan_file(path)
        if accesses:
            current[rel] = accesses
    return current


def _counter(accesses: list[BrainAccess]) -> Counter[str]:
    return Counter(access.attr for access in accesses)


def main() -> int:
    if not SERVICES_DIR.exists():
        print(f"[domain-service-brain-boundary] skip: {SERVICES_DIR} not present")
        return 0

    current = _current_accesses()
    violations: list[str] = []

    for rel, accesses in sorted(current.items()):
        current_counts = _counter(accesses)
        baseline_counts = BASELINE.get(rel, {})
        for attr, count in sorted(current_counts.items()):
            allowed = baseline_counts.get(attr, 0)
            if count <= allowed:
                continue
            examples = [
                access
                for access in accesses
                if access.attr == attr
            ][:3]
            sample = "; ".join(f"L{a.line}: {a.text}" for a in examples)
            if allowed == 0:
                violations.append(
                    f"{rel}: new self.brain.{attr} access ({count} occurrence(s)); {sample}"
                )
            else:
                violations.append(
                    f"{rel}: self.brain.{attr} grew from {allowed} to {count}; {sample}"
                )

    current_total = sum(sum(_counter(accesses).values()) for accesses in current.values())
    baseline_total = sum(sum(attrs.values()) for attrs in BASELINE.values())

    if violations:
        print(
            "[domain-service-brain-boundary] FAIL: domain service BrainService "
            f"back-channel grew ({len(violations)} violation(s))"
        )
        for violation in violations[:25]:
            print(f"  - {violation}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        print()
        print("  hint: domain services must receive narrow ports/repos instead of adding")
        print("        new self.brain.<attr> calls. If an existing access is removed,")
        print("        shrink BASELINE in this script in the same change.")
        return 1

    print(
        "[domain-service-brain-boundary] OK: no new domain service BrainService "
        f"back-channel access (current {current_total} <= baseline {baseline_total})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
