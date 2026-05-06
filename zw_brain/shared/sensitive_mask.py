"""Read-side sensitive field mask layer.

Per [2026-05-06] policy override: business-visible sensitive fields (name / phone / email
/ id_card / address) are ingested raw into canonical / projection records; this module
masks them on the way out to any read surface (Skill response, WebUI BFF, Dashboard
projection, log line, audit receipt content, export file).

Real secrets (password / token / key / connection string) are dropped at the mapper
boundary and never reach the masker — see `zw_brain.shared.sanitization.safe_json` and
the mapper-level DROP_FIELDS sets.

Roles & strength
----------------

`role` decides how aggressively to mask. Anything not in the table is treated as
`external` (safest default — must opt up explicitly, in line with §〇.2):

    role                 phone           name        email                id_card     address
    -------------------  --------------  ----------  -------------------  ----------  ---------
    internal_admin       full            full        full                 full        full
    internal_viewer      138****1111     张*         z***@sd.gov.cn       370***1234  ***
    external (default)   138****1111     张*         z***@***             ********    ***

Both `internal_viewer` and `external` produce safe output; the difference is
`internal_viewer` keeps the email host visible for support workflows. Add new roles by
extending `MASK_PROFILES`.

Usage at boundaries
-------------------

    from zw_brain.shared.sensitive_mask import apply_field_masks

    safe_payload = apply_field_masks(actor.profile_json, role="internal_viewer")
    return {"actor": {"display_name": mask_name(actor.display_name, role=role), ...,
                      "profile": safe_payload}}

Apply once per read; double-masking is idempotent but wasteful.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Field-key → mask-kind hints. Keys are lowercased and matched exactly OR by suffix
# (so `contact_phone`, `phone_no`, `mobile_phone` all resolve to "phone").
# Values are mask-kind strings the dispatcher knows about.
# ---------------------------------------------------------------------------
# Exact-match hints. Required for keys whose stem is too generic to suffix-match safely
# (e.g. `name` vs `region_name` / `org_name` / `system_name` — only the bare `name`
# is sensitive; the qualifier-prefixed forms are not).
EXACT_MASK_HINTS: dict[str, str] = {
    # phone / mobile
    "phone": "phone",
    "mobile": "phone",
    "tel": "phone",
    "telephone": "phone",
    "contact_phone": "phone",
    "contact_mobile": "phone",
    "contact_tel": "phone",
    # personal name (only listed forms — generic "*_name" suffix is not auto-masked)
    "name": "name",
    "contact_name": "name",
    "creator_name": "name",
    "display_name": "name",
    "applicant_name": "name",
    "handler_name": "name",
    "real_name": "name",
    "person_name": "name",
    # email
    "email": "email",
    "contact_email": "email",
    "mail": "email",
    # id_card
    "id_card": "id_card",
    "idcard": "id_card",
    "identity_num": "id_card",
    "identity_id": "id_card",
    "id_number": "id_card",
    # address
    "address": "address",
    "addr": "address",
    "contact_address": "address",
    "home_address": "address",
}

# Suffix-match hints. The leading underscore is required so that, e.g., `org_name` does
# NOT match `_name` (`_name` is intentionally absent from this map).
SUFFIX_MASK_HINTS: dict[str, str] = {
    "_phone": "phone",
    "_mobile": "phone",
    "_tel": "phone",
    "_email": "email",
    "_mail": "email",
    "_id_card": "id_card",
    "_idcard": "id_card",
    "_identity_num": "id_card",
    "_address": "address",
}

# Backwards-compat alias kept for any external readers; intentionally points at the
# exact-match table — suffix matching is now opt-in via SUFFIX_MASK_HINTS.
DEFAULT_MASK_HINTS: dict[str, str] = EXACT_MASK_HINTS

# Roles → per-mask-kind strength (level 0 = full, 1 = light, 2 = strong)
MASK_PROFILES: dict[str, dict[str, int]] = {
    "internal_admin": {"phone": 0, "name": 0, "email": 0, "id_card": 0, "address": 0},
    "internal_viewer": {"phone": 1, "name": 1, "email": 1, "id_card": 1, "address": 2},
    "external": {"phone": 1, "name": 1, "email": 2, "id_card": 2, "address": 2},
}
DEFAULT_ROLE = "external"


def _level_for(role: str, kind: str) -> int:
    profile = MASK_PROFILES.get(role) or MASK_PROFILES[DEFAULT_ROLE]
    return profile.get(kind, MASK_PROFILES[DEFAULT_ROLE].get(kind, 2))


# ---------------------------------------------------------------------------
# Atomic mask functions. Each accepts a string-or-None and returns the masked form.
# Non-string types are returned unchanged (defensive — callers may pass bytes, ints, …).
# ---------------------------------------------------------------------------

def mask_phone(value: Any, *, role: str = DEFAULT_ROLE) -> Any:
    if not isinstance(value, str) or not value:
        return value
    level = _level_for(role, "phone")
    if level == 0:
        return value
    digits_only = "".join(ch for ch in value if ch.isdigit())
    if len(digits_only) >= 7:
        return f"{digits_only[:3]}****{digits_only[-4:]}"
    if len(digits_only) >= 3:
        return f"{digits_only[:2]}***"
    return "***"


def mask_name(value: Any, *, role: str = DEFAULT_ROLE) -> Any:
    if not isinstance(value, str) or not value:
        return value
    level = _level_for(role, "name")
    if level == 0:
        return value
    text = value.strip()
    if not text:
        return text
    # Chinese names: keep first character, replace remainder with `*`
    if any("一" <= ch <= "鿿" for ch in text):
        return text[0] + "*" * (len(text) - 1) if len(text) > 1 else text + "*"
    # Latin: keep first letter only
    if len(text) <= 1:
        return text + "*"
    return text[0] + "*" * (len(text) - 1)


def mask_email(value: Any, *, role: str = DEFAULT_ROLE) -> Any:
    if not isinstance(value, str) or "@" not in value:
        return value
    level = _level_for(role, "email")
    if level == 0:
        return value
    local, _, host = value.partition("@")
    if not local:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    if level >= 2:
        return f"{masked_local}@***"
    return f"{masked_local}@{host}"


def mask_id_card(value: Any, *, role: str = DEFAULT_ROLE) -> Any:
    if not isinstance(value, str) or not value:
        return value
    level = _level_for(role, "id_card")
    if level == 0:
        return value
    if level >= 2:
        return "*" * len(value)
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


def mask_address(value: Any, *, role: str = DEFAULT_ROLE) -> Any:
    if not isinstance(value, str) or not value:
        return value
    level = _level_for(role, "address")
    if level == 0:
        return value
    if level >= 2:
        return "***"
    # level 1: keep prefix (province/city head, ~6 chars) and tail
    if len(value) <= 6:
        return "***"
    return value[:6] + "***"


_DISPATCH = {
    "phone": mask_phone,
    "name": mask_name,
    "email": mask_email,
    "id_card": mask_id_card,
    "address": mask_address,
}


def mask_value(value: Any, kind: str, *, role: str = DEFAULT_ROLE) -> Any:
    """Mask a single scalar by explicit kind."""
    fn = _DISPATCH.get(kind)
    if fn is None:
        return value
    return fn(value, role=role)


def _resolve_kind(key: str, field_policy: dict[str, str] | None) -> str | None:
    """Return mask-kind for `key`, or None if no rule applies.

    Resolution order:
      1. caller-provided field_policy[lowercase key] (may be empty string to opt out)
      2. EXACT_MASK_HINTS[lowercase key]
      3. SUFFIX_MASK_HINTS — match via underscore-bounded suffix (e.g.
         `home_phone` → "phone"). Bare `name` / `addr` are NOT suffix hints; they must
         be added to EXACT_MASK_HINTS to be picked up.
    """
    if not key:
        return None
    lk = key.lower()
    if field_policy is not None and lk in field_policy:
        kind = field_policy[lk]
        return kind or None
    if lk in EXACT_MASK_HINTS:
        return EXACT_MASK_HINTS[lk]
    for suffix, kind in SUFFIX_MASK_HINTS.items():
        if lk.endswith(suffix):
            return kind
    return None


def apply_field_masks(
    value: Any,
    *,
    field_policy: dict[str, str] | None = None,
    role: str = DEFAULT_ROLE,
    _parent_key: str | None = None,
) -> Any:
    """Recursively mask sensitive fields by walking dict/list payloads.

    - dict: walk each (key, value); apply mask if key resolves to a mask-kind, otherwise
      recurse into the value
    - list / tuple: recurse into items (parent key carries forward, e.g. `phones=[...]`
      where each entry is masked as a phone)
    - str: mask only if a parent key resolved to a mask-kind (otherwise return as-is)
    - other: return unchanged

    `field_policy` lets callers override per-key behavior (lower-case keys). Set the
    value to an empty string to suppress default masking for that key.
    """
    if isinstance(value, dict):
        return {k: apply_field_masks(v, field_policy=field_policy, role=role, _parent_key=k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [apply_field_masks(item, field_policy=field_policy, role=role, _parent_key=_parent_key) for item in value]
        return items if isinstance(value, list) else tuple(items)
    if _parent_key is not None and isinstance(value, str):
        kind = _resolve_kind(_parent_key, field_policy)
        if kind is not None:
            return mask_value(value, kind, role=role)
    return value
