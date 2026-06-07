#!/usr/bin/env python3
"""check_g4_acceptance_deadline — debt predicate for G4「受理已过期」维度可行性.

现算依据（纯源码静态检查，不需 live DB，确定性）：G4「受理已过期」待办维度需要 application 级
**受理截止期/办理时限**字段。真库核查结论：`ApplicationRecord`（zw_brain/domain/models.py）字段 =
id/tenant_id/application_code/status/applicant_name/applicant_org/payload_json/submitted_at/
created_at/updated_at —— 无受理截止期/超时/有效期字段。唯一 `due_at` 在 ApprovalStepRecord（审批
步骤级，非受理级）且全仓零写入。故 G4 过期维度无真实上游数据可算，记债等上游补供。

predicate `acceptance_deadline_debt_open()`:
  True  (debt OPEN)  ⇔ ApplicationRecord 无受理截止期字段
  False (stale-fixed) ⇔ ApplicationRecord 已含截止期/办理时限字段（上游补供后自动关债）
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "zw_brain" / "domain" / "models.py"
CLASS_NAME = "ApplicationRecord"

# 受理截止期/办理时限语义字段锚点（任一 mapped_column 命中即视为已承载该维度）。
DEADLINE_FIELD_ANCHORS: tuple[str, ...] = (
    "due_at",
    "deadline",
    "expire_at",
    "expires_at",
    "expiry",
    "valid_until",
    "accept_deadline",
    "acceptance_deadline",
    "process_deadline",
    "handle_deadline",
    "overdue_at",
    "timeout_at",
)


def _class_block(source: str, class_name: str) -> str:
    m = re.search(rf"class {re.escape(class_name)}\(Base\):(.*?)(?:\nclass |\Z)", source, re.S)
    return m.group(1) if m else ""


def _mapped_column_field_names(block: str) -> set[str]:
    """Extract field names that are mapped_column(...) declarations in a class block."""
    return set(re.findall(r"^\s*(\w+)\s*:\s*Mapped\[[^\]]*\]\s*=\s*mapped_column", block, re.M))


def has_acceptance_deadline_field() -> bool:
    if not MODELS.exists():
        return False
    block = _class_block(MODELS.read_text(encoding="utf-8"), CLASS_NAME)
    if not block:
        return False
    fields = {f.lower() for f in _mapped_column_field_names(block)}
    return any(any(a in f for a in DEADLINE_FIELD_ANCHORS) for f in fields)


def acceptance_deadline_debt_open() -> bool:
    """True ⇔ ApplicationRecord carries no acceptance-deadline field (debt open)."""
    return not has_acceptance_deadline_field()


if __name__ == "__main__":
    present = has_acceptance_deadline_field()
    print(f"[g4-acceptance-deadline] {CLASS_NAME} 受理截止期字段{'存在' if present else '缺失'} → debt {'stale-fixed' if present else 'OPEN'}")
