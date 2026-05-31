"""debt_status_lib — single source of truth for preflight-debt status (D46-isomorph).

Debt status is NOT stored; it is a function of each debt entry's *assert* run
against the live tree, exactly as feature status is a function of SPEC+MEASUREMENT+
SIGN-OFF (feature_status_lib.py). Mirrors that architecture so debt can never rot
into a hand-maintained list that disagrees with the code.

Inputs: .testing/debt/<slug>.debt.yaml — one file per debt entry. Each carries a
single `assert` describing *what keeps this debt open*. Running the assert derives:

  open        — the assert's open-condition still holds (debt is real, keep it).
  stale-fixed — the open-condition no longer holds (the thing it tracked is gone;
                the debt is dead and should be closed).
  invalid     — the debt entry is malformed, or its script assert errored, or an
                `external` debt is missing the required owner+trigger.

Assert kinds (anchor-semantic, never line-number — guards D18):
  grep_present  {file, pattern}  open  ⇔ pattern present  in file
  grep_absent   {file, pattern}  open  ⇔ pattern absent from file
  script        {module, predicate}  open ⇔ predicate() truthy (False→stale, raise→invalid)
  external      {}  (no code assert)  always open; MUST carry owner + trigger
"""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEBT_DIR = REPO_ROOT / ".testing" / "debt"
DEBT_GLOB = "*.debt.yaml"

REQUIRED_FIELDS = ("slug", "title", "date", "severity", "assert")
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_KINDS = {"grep_present", "grep_absent", "script", "external"}

OPEN = "open"
STALE_FIXED = "stale-fixed"
INVALID = "invalid"


@dataclass
class DebtStatus:
    slug: str
    path: str
    title: str = ""
    date: str = ""
    severity: str = ""
    kind: str = ""
    state: str = INVALID
    detail: str = ""
    owner: str | None = None
    trigger: str | None = None


def _load_yaml(path: Path) -> dict:
    import yaml  # noqa: PLC0415

    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def discover_debts() -> list[Path]:
    if not DEBT_DIR.exists():
        return []
    return sorted(DEBT_DIR.glob(DEBT_GLOB))


def validate_schema(data: dict) -> str | None:
    """Return an error string if the debt doc is malformed, else None."""
    for fieldname in REQUIRED_FIELDS:
        if fieldname not in data or data.get(fieldname) in (None, ""):
            return f"missing required field: {fieldname}"
    if str(data.get("severity")) not in VALID_SEVERITIES:
        return f"invalid severity: {data.get('severity')} (allowed {sorted(VALID_SEVERITIES)})"
    assertion = data.get("assert")
    if not isinstance(assertion, dict):
        return "assert must be a mapping"
    kind = assertion.get("kind")
    if kind not in VALID_KINDS:
        return f"invalid assert.kind: {kind} (allowed {sorted(VALID_KINDS)})"
    if kind in ("grep_present", "grep_absent"):
        if not assertion.get("file") or not assertion.get("pattern"):
            return f"assert.kind={kind} requires file + pattern"
    if kind == "script":
        if not assertion.get("module") or not assertion.get("predicate"):
            return "assert.kind=script requires module + predicate"
    if kind == "external":
        if not data.get("owner") or not data.get("trigger"):
            return "assert.kind=external requires owner + trigger"
    return None


def _grep_present(file_rel: str, pattern: str) -> tuple[bool, str]:
    """Return (present, detail). Anchor-semantic: regex over file text, no line numbers."""
    target = REPO_ROOT / file_rel
    if not target.exists():
        return False, f"file absent: {file_rel}"
    text = target.read_text(encoding="utf-8", errors="replace")
    rx = re.compile(pattern, re.MULTILINE)
    present = rx.search(text) is not None
    return present, f"pattern {'present' if present else 'absent'} in {file_rel}"


def _run_script_predicate(module_rel: str, predicate: str) -> tuple[bool, str]:
    """Import scripts/<module> and call predicate() -> bool. Raise → caller marks invalid."""
    mod_path = REPO_ROOT / module_rel
    if not mod_path.exists():
        raise FileNotFoundError(f"script module absent: {module_rel}")
    spec = importlib.util.spec_from_file_location(f"_debt_pred_{mod_path.stem}", mod_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {module_rel}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, predicate, None)
    if fn is None or not callable(fn):
        raise AttributeError(f"{module_rel} has no callable {predicate}")
    return bool(fn()), f"{module_rel}:{predicate}()"


def evaluate(path: Path) -> DebtStatus:
    data = _load_yaml(path)
    rel = str(path.relative_to(REPO_ROOT))
    slug = str(data.get("slug") or path.stem.replace(".debt", ""))
    st = DebtStatus(
        slug=slug,
        path=rel,
        title=str(data.get("title", "")),
        date=str(data.get("date", "")),
        severity=str(data.get("severity", "")),
        owner=data.get("owner"),
        trigger=data.get("trigger"),
    )
    err = validate_schema(data)
    if err is not None:
        st.state = INVALID
        st.detail = err
        return st
    assertion = data["assert"]
    st.kind = str(assertion.get("kind"))
    try:
        if st.kind == "grep_present":
            present, detail = _grep_present(str(assertion["file"]), str(assertion["pattern"]))
            st.state = OPEN if present else STALE_FIXED
            st.detail = detail
        elif st.kind == "grep_absent":
            present, detail = _grep_present(str(assertion["file"]), str(assertion["pattern"]))
            # open ⇔ pattern absent (the fix it tracks is not yet in place)
            st.state = OPEN if not present else STALE_FIXED
            st.detail = detail
        elif st.kind == "script":
            still_open, detail = _run_script_predicate(str(assertion["module"]), str(assertion["predicate"]))
            st.state = OPEN if still_open else STALE_FIXED
            st.detail = detail
        elif st.kind == "external":
            st.state = OPEN
            st.detail = f"external — owner={st.owner}; trigger={st.trigger}"
    except Exception as exc:  # noqa: BLE001 — any assert error ⇒ invalid (fail-closed)
        st.state = INVALID
        st.detail = f"assert error: {type(exc).__name__}: {exc}"
    return st


def compute_statuses() -> list[DebtStatus]:
    return [evaluate(path) for path in discover_debts()]
