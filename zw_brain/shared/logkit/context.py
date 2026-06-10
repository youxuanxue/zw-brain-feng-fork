from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

_REQUEST_ID: ContextVar[str] = ContextVar("zw_brain_log_request_id", default="")
_ENTRY: ContextVar[str] = ContextVar("zw_brain_log_entry", default="")
_ACTOR: ContextVar[str] = ContextVar("zw_brain_log_actor", default="")

# Client-supplied ids are echoed into log lines and the X-Request-Id response header;
# constrain the alphabet so a hostile header cannot inject log/header content.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_request_id() -> str:
    # "req-" namespace keeps trace ids visually distinct from business REQ-*/AE-* ids.
    return f"req-{uuid.uuid4().hex[:16]}"


def bind_request_context(
    request_id: str | None = None, *, entry: str = ""
) -> tuple[Token[str], ...]:
    rid = (request_id or "").strip()
    if not _REQUEST_ID_PATTERN.match(rid):
        rid = new_request_id()
    return (_REQUEST_ID.set(rid), _ENTRY.set(entry), _ACTOR.set(""))


def reset_request_context(tokens: tuple[Token[str], ...]) -> None:
    for var, token in zip((_REQUEST_ID, _ENTRY, _ACTOR), tokens, strict=False):
        var.reset(token)


def get_request_id() -> str:
    return _REQUEST_ID.get()


def get_log_entry() -> str:
    return _ENTRY.get()


def get_log_actor() -> str:
    return _ACTOR.get()


def set_log_actor(actor: str) -> None:
    _ACTOR.set(actor or "")
