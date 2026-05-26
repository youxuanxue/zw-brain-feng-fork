from __future__ import annotations

from contextvars import ContextVar, Token

# Per-request UI role. Previously stashed on the process-global BrainService
# singleton (`_ui_state["role"]`), where concurrent requests overwrote each
# other's role between resolve and read. A ContextVar isolates the value per
# thread / asyncio task, so each request sees only its own role.
DEFAULT_ROLE = "ROLE_ORGAN_OPERATER"

_CURRENT_ROLE: ContextVar[str | None] = ContextVar("zw_brain_current_role", default=None)


def set_current_role(role: str) -> Token[str | None]:
    return _CURRENT_ROLE.set(role)


def get_current_role(default: str = DEFAULT_ROLE) -> str:
    value = _CURRENT_ROLE.get()
    return value if value is not None else default


def reset_current_role(token: Token[str | None]) -> None:
    _CURRENT_ROLE.reset(token)
