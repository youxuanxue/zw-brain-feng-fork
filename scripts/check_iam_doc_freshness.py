#!/usr/bin/env python3
"""check_iam_doc_freshness.py

Mechanical guard against `docs/iam-login-logout-implementation.md` drifting back to the pre-BFF
model. The BFF refactor (PR #53) moves IAM tokens to a server-side session store bound to an
HttpOnly cookie. The pre-BFF doc described `sessionStorage` token storage and `Authorization: Bearer`
on `/api/*` — patterns the code no longer follows.

This check is intentionally narrow: it greps the doc for code-shape claims that are demonstrably
false in the current implementation. It does NOT enforce stylistic preferences.

Anchor exemptions: each forbidden pattern accepts an explicit override on the same line via the
marker `[doc-historical-context]` so the doc can still discuss the old model in evolution notes.

Exit codes:
- 0: doc is consistent with BFF model
- 1: stale claim detected; failure message identifies file:line and offending substring
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC_PATH = REPO / "docs" / "iam-login-logout-implementation.md"

EXEMPTION_MARKER = "[doc-historical-context]"

FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Authorization\s*:\s*Bearer\s+<access_token>", re.IGNORECASE),
     "Stale: /api/* on cookie path uses session lookup, not Authorization Bearer."),
    (re.compile(r"将\s*(返回的)?\s*token\s*写入\s*[`']?sessionStorage"),
     "Stale: tokens no longer reach the browser; only public snapshot lands in sessionStorage."),
    (re.compile(r"前端持\s*token", re.IGNORECASE),
     "Stale: BFF model keeps tokens server-side; phrase implies sessionStorage token storage."),
    (re.compile(r"从\s*[`']?sessionStorage[`']?\s*读取\s*[`']?access_token"),
     "Stale: access_token never lives in sessionStorage under the BFF model."),
    (re.compile(r"refresh\s+token\s+换\s*新\s*access\s+token.*?更新\s*[`']?sessionStorage", re.IGNORECASE),
     "Stale: refresh stores the new token server-side; sessionStorage only sees the public payload."),
]


def main() -> int:
    if not DOC_PATH.exists():
        print(f"check_iam_doc_freshness: FAIL — missing {DOC_PATH.relative_to(REPO)}")
        return 1

    text = DOC_PATH.read_text(encoding="utf-8")
    failures: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if EXEMPTION_MARKER in line:
            continue
        for pattern, reason in FORBIDDEN_PATTERNS:
            match = pattern.search(line)
            if match:
                snippet = match.group(0)
                failures.append(
                    f"  - {DOC_PATH.relative_to(REPO)}:{line_no}: {reason}\n      offending: {snippet!r}"
                )

    if failures:
        print("check_iam_doc_freshness: FAIL")
        for entry in failures:
            print(entry)
        print(
            "\nIf a stale pattern is legitimately referenced as historical context, append "
            f"{EXEMPTION_MARKER} to that line and re-run."
        )
        return 1

    print("check_iam_doc_freshness: OK (no pre-BFF claims detected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
