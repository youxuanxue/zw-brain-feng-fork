from __future__ import annotations

import copy
import secrets
import threading
import time
from dataclasses import dataclass, replace
from typing import Any

from zw_brain.shared.sanitization import safe_json

SESSION_COOKIE_NAME = "zw_brain_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_REFRESH_THRESHOLD_SECONDS = 60
_DEFAULT_ACCESS_LIFETIME_SECONDS = 300
_DEFAULT_REFRESH_LIFETIME_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    csrf_token: str
    token_payload: dict[str, Any]
    claims: dict[str, Any]
    actor_snapshot: dict[str, Any]
    audit_id: str
    created_at: float
    updated_at: float
    expires_at: float
    refresh_expires_at: float
    development_iam_bypass: bool = False

    @property
    def access_token(self) -> str:
        return str(self.token_payload.get("access_token") or "")

    @property
    def refresh_token(self) -> str:
        return str(self.token_payload.get("refresh_token") or "")

    @property
    def id_token(self) -> str:
        return str(self.token_payload.get("id_token") or "")

    def public_payload(self) -> dict[str, Any]:
        # Browser response body intentionally omits access_token / refresh_token / id_token —
        # the cookie carries the session id and the server resolves tokens internally.
        return {
            "authenticated": True,
            "actor_snapshot": safe_json(self.actor_snapshot),
            "audit_id": self.audit_id,
            "expires_at": int(self.expires_at),
            "csrf_token": self.csrf_token,
            "development_iam_bypass": self.development_iam_bypass,
        }


class AuthSessionStore:
    """Single-process thread-safe in-memory session store. Multi-process deployments need an
    out-of-process backend (Redis/DB); see docs/preflight-debt.md."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, AuthSession] = {}

    def create(
        self,
        *,
        token_payload: dict[str, Any],
        claims: dict[str, Any],
        actor_snapshot: dict[str, Any],
        audit_id: str,
        development_iam_bypass: bool = False,
    ) -> AuthSession:
        now = time.time()
        session = AuthSession(
            session_id=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            token_payload=copy.deepcopy(token_payload),
            claims=safe_json(claims),
            actor_snapshot=safe_json(actor_snapshot),
            audit_id=str(audit_id or ""),
            created_at=now,
            updated_at=now,
            expires_at=self._expiry(now, token_payload.get("expires_in"), default_seconds=_DEFAULT_ACCESS_LIFETIME_SECONDS),
            refresh_expires_at=self._expiry(now, token_payload.get("refresh_expires_in"), default_seconds=_DEFAULT_REFRESH_LIFETIME_SECONDS),
            development_iam_bypass=bool(development_iam_bypass),
        )
        with self._lock:
            self._purge_expired(now)
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AuthSession | None:
        now = time.time()
        with self._lock:
            self._purge_expired(now)
            session = self._sessions.get(str(session_id or ""))
            if session is None:
                return None
            if session.refresh_expires_at <= now:
                self._sessions.pop(session.session_id, None)
                return None
            return session

    def update_actor_snapshot(self, session_id: str, actor_snapshot: dict[str, Any]) -> AuthSession | None:
        now = time.time()
        with self._lock:
            current = self._sessions.get(str(session_id or ""))
            if current is None or current.refresh_expires_at <= now:
                if current is not None:
                    self._sessions.pop(current.session_id, None)
                return None
            session = replace(
                current,
                actor_snapshot=safe_json(actor_snapshot),
                updated_at=now,
            )
            self._sessions[session.session_id] = session
            return session

    def update_tokens(
        self,
        session_id: str,
        *,
        token_payload: dict[str, Any],
        claims: dict[str, Any] | None = None,
    ) -> AuthSession | None:
        now = time.time()
        with self._lock:
            current = self._sessions.get(str(session_id or ""))
            if current is None or current.refresh_expires_at <= now:
                if current is not None:
                    self._sessions.pop(current.session_id, None)
                return None
            merged = dict(current.token_payload)
            merged.update(copy.deepcopy(token_payload))
            next_claims = safe_json(claims) if claims is not None else current.claims
            access_default = max(int(current.expires_at - now), 1)
            refresh_default = max(int(current.refresh_expires_at - now), 1)
            session = replace(
                current,
                token_payload=merged,
                claims=next_claims,
                updated_at=now,
                expires_at=self._expiry(now, token_payload.get("expires_in"), default_seconds=access_default),
                refresh_expires_at=self._expiry(now, token_payload.get("refresh_expires_in"), default_seconds=refresh_default),
            )
            self._sessions[session.session_id] = session
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(str(session_id or ""), None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    @staticmethod
    def should_refresh(session: AuthSession) -> bool:
        return session.expires_at - time.time() < SESSION_REFRESH_THRESHOLD_SECONDS and bool(session.refresh_token)

    @staticmethod
    def _expiry(now: float, value: Any, *, default_seconds: int) -> float:
        try:
            seconds = int(float(value))
        except (TypeError, ValueError):
            seconds = default_seconds
        return now + max(seconds, 1)

    def _purge_expired(self, now: float) -> None:
        expired = [sid for sid, session in self._sessions.items() if session.refresh_expires_at <= now]
        for sid in expired:
            self._sessions.pop(sid, None)
