from __future__ import annotations

import copy
import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol, runtime_checkable

from zw_brain.shared.sanitization import safe_json

SESSION_COOKIE_NAME = "zw_brain_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_REFRESH_THRESHOLD_SECONDS = 60
DEFAULT_SESSION_REDIS_KEY_PREFIX = "zw-brain:session:"
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
            "claims": self._public_claims(),
        }

    def _public_claims(self) -> dict[str, Any]:
        claims = self.claims if isinstance(self.claims, dict) else {}
        public: dict[str, Any] = {}
        for key in ("sub", "preferred_username", "email", "org_code", "exp"):
            if claims.get(key) is not None:
                public[key] = claims[key]
        for key in ("realm_access", "resource_access"):
            if isinstance(claims.get(key), (dict, list)):
                public[key] = safe_json(claims[key])
        return public

    def to_storage_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_storage_dict(cls, payload: dict[str, Any]) -> AuthSession:
        return cls(
            session_id=str(payload["session_id"]),
            csrf_token=str(payload["csrf_token"]),
            token_payload=dict(payload.get("token_payload") or {}),
            claims=dict(payload.get("claims") or {}),
            actor_snapshot=dict(payload.get("actor_snapshot") or {}),
            audit_id=str(payload.get("audit_id") or ""),
            created_at=float(payload["created_at"]),
            updated_at=float(payload["updated_at"]),
            expires_at=float(payload["expires_at"]),
            refresh_expires_at=float(payload["refresh_expires_at"]),
            development_iam_bypass=bool(payload.get("development_iam_bypass")),
        )


@runtime_checkable
class AuthSessionStoreProtocol(Protocol):
    def create(
        self,
        *,
        token_payload: dict[str, Any],
        claims: dict[str, Any],
        actor_snapshot: dict[str, Any],
        audit_id: str,
        development_iam_bypass: bool = False,
    ) -> AuthSession: ...

    def get(self, session_id: str) -> AuthSession | None: ...

    def update_actor_snapshot(self, session_id: str, actor_snapshot: dict[str, Any]) -> AuthSession | None: ...

    def update_tokens(
        self,
        session_id: str,
        *,
        token_payload: dict[str, Any],
        claims: dict[str, Any] | None = None,
    ) -> AuthSession | None: ...

    def delete(self, session_id: str) -> None: ...

    def clear(self) -> None: ...

    @staticmethod
    def should_refresh(session: AuthSession) -> bool: ...


def session_expiry(now: float, value: Any, *, default_seconds: int) -> float:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        seconds = default_seconds
    return now + max(seconds, 1)


def build_auth_session(
    *,
    token_payload: dict[str, Any],
    claims: dict[str, Any],
    actor_snapshot: dict[str, Any],
    audit_id: str,
    development_iam_bypass: bool = False,
) -> AuthSession:
    now = time.time()
    return AuthSession(
        session_id=secrets.token_urlsafe(32),
        csrf_token=secrets.token_urlsafe(32),
        token_payload=copy.deepcopy(token_payload),
        claims=safe_json(claims),
        actor_snapshot=safe_json(actor_snapshot),
        audit_id=str(audit_id or ""),
        created_at=now,
        updated_at=now,
        expires_at=session_expiry(now, token_payload.get("expires_in"), default_seconds=_DEFAULT_ACCESS_LIFETIME_SECONDS),
        refresh_expires_at=session_expiry(
            now,
            token_payload.get("refresh_expires_in"),
            default_seconds=_DEFAULT_REFRESH_LIFETIME_SECONDS,
        ),
        development_iam_bypass=bool(development_iam_bypass),
    )


class InMemoryAuthSessionStore:
    """Thread-safe in-memory session store for single-process dev/demo."""

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
        session = build_auth_session(
            token_payload=token_payload,
            claims=claims,
            actor_snapshot=actor_snapshot,
            audit_id=audit_id,
            development_iam_bypass=development_iam_bypass,
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
                expires_at=session_expiry(now, token_payload.get("expires_in"), default_seconds=access_default),
                refresh_expires_at=session_expiry(
                    now,
                    token_payload.get("refresh_expires_in"),
                    default_seconds=refresh_default,
                ),
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

    def _purge_expired(self, now: float) -> None:
        expired = [sid for sid, session in self._sessions.items() if session.refresh_expires_at <= now]
        for sid in expired:
            self._sessions.pop(sid, None)


class RedisAuthSessionStore:
    """Out-of-process session store for multi-worker / multi-replica REST deployments."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        client: Any | None = None,
        key_prefix: str = DEFAULT_SESSION_REDIS_KEY_PREFIX,
    ) -> None:
        if client is not None:
            self._client = client
        elif redis_url:
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError(
                    "ZW_BRAIN_SESSION_REDIS_URL is set but the 'redis' package is not installed. "
                    "Install with: uv pip install 'zw-brain[redis]'"
                ) from exc
            self._client = redis.from_url(redis_url, decode_responses=True)
        else:
            raise ValueError("redis_url or client is required")
        self._key_prefix = key_prefix

    def create(
        self,
        *,
        token_payload: dict[str, Any],
        claims: dict[str, Any],
        actor_snapshot: dict[str, Any],
        audit_id: str,
        development_iam_bypass: bool = False,
    ) -> AuthSession:
        session = build_auth_session(
            token_payload=token_payload,
            claims=claims,
            actor_snapshot=actor_snapshot,
            audit_id=audit_id,
            development_iam_bypass=development_iam_bypass,
        )
        self._save(session)
        return session

    def get(self, session_id: str) -> AuthSession | None:
        raw = self._client.get(self._key(session_id))
        if not raw:
            return None
        session = AuthSession.from_storage_dict(json.loads(raw))
        now = time.time()
        if session.refresh_expires_at <= now:
            self.delete(session.session_id)
            return None
        return session

    def update_actor_snapshot(self, session_id: str, actor_snapshot: dict[str, Any]) -> AuthSession | None:
        current = self.get(session_id)
        if current is None:
            return None
        now = time.time()
        session = replace(
            current,
            actor_snapshot=safe_json(actor_snapshot),
            updated_at=now,
        )
        self._save(session)
        return session

    def update_tokens(
        self,
        session_id: str,
        *,
        token_payload: dict[str, Any],
        claims: dict[str, Any] | None = None,
    ) -> AuthSession | None:
        current = self.get(session_id)
        if current is None:
            return None
        now = time.time()
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
            expires_at=session_expiry(now, token_payload.get("expires_in"), default_seconds=access_default),
            refresh_expires_at=session_expiry(
                now,
                token_payload.get("refresh_expires_in"),
                default_seconds=refresh_default,
            ),
        )
        self._save(session)
        return session

    def delete(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))

    def clear(self) -> None:
        cursor = 0
        pattern = f"{self._key_prefix}*"
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break

    @staticmethod
    def should_refresh(session: AuthSession) -> bool:
        return InMemoryAuthSessionStore.should_refresh(session)

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    def _ttl_seconds(self, session: AuthSession) -> int:
        return max(int(session.refresh_expires_at - time.time()), 1)

    def _save(self, session: AuthSession) -> None:
        ttl = self._ttl_seconds(session)
        if ttl <= 0:
            self.delete(session.session_id)
            return
        self._client.setex(self._key(session.session_id), ttl, json.dumps(session.to_storage_dict()))


# Backward-compatible alias used across tests and docs.
AuthSessionStore = InMemoryAuthSessionStore


def get_session_redis_url() -> str:
    return os.environ.get("ZW_BRAIN_SESSION_REDIS_URL", "").strip()


def get_session_redis_key_prefix() -> str:
    return os.environ.get("ZW_BRAIN_SESSION_REDIS_KEY_PREFIX", DEFAULT_SESSION_REDIS_KEY_PREFIX).strip() or DEFAULT_SESSION_REDIS_KEY_PREFIX


def create_auth_session_store() -> AuthSessionStoreProtocol:
    redis_url = get_session_redis_url()
    if redis_url:
        return RedisAuthSessionStore(redis_url, key_prefix=get_session_redis_key_prefix())
    return InMemoryAuthSessionStore()


def validate_session_store_for_deploy() -> None:
    mode = os.environ.get("ZW_BRAIN_DEPLOY_MODE", "").strip().lower()
    if mode not in {"prod", "production"}:
        return
    if get_session_redis_url():
        return
    raise SystemExit(
        "ZW_BRAIN_DEPLOY_MODE=prod requires ZW_BRAIN_SESSION_REDIS_URL "
        "(BFF HttpOnly sessions must be shared across REST replicas)."
    )
