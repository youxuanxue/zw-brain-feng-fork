from __future__ import annotations

import time

import pytest

from zw_brain.shared.auth_session import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SESSION_REFRESH_THRESHOLD_SECONDS,
    AuthSession,
    AuthSessionStore,
)


def _make_token_payload(*, access: str = "access-1", refresh: str = "refresh-1", expires_in: int = 300, refresh_expires_in: int = 3600, id_token: str = "id-1") -> dict:
    return {
        "access_token": access,
        "refresh_token": refresh,
        "id_token": id_token,
        "expires_in": expires_in,
        "refresh_expires_in": refresh_expires_in,
        "token_type": "Bearer",
    }


def test_constants_stable() -> None:
    assert SESSION_COOKIE_NAME == "zw_brain_session"
    assert CSRF_HEADER_NAME == "X-CSRF-Token"
    assert SESSION_REFRESH_THRESHOLD_SECONDS == 60


def test_create_returns_session_with_random_ids() -> None:
    store = AuthSessionStore()
    a = store.create(token_payload=_make_token_payload(), claims={"sub": "u1"}, actor_snapshot={"subject": "u1"}, audit_id="audit-1")
    b = store.create(token_payload=_make_token_payload(), claims={"sub": "u2"}, actor_snapshot={"subject": "u2"}, audit_id="audit-2")
    assert a.session_id != b.session_id
    assert a.csrf_token != b.csrf_token
    assert len(a.session_id) >= 32
    assert len(a.csrf_token) >= 32


def test_get_returns_same_session() -> None:
    store = AuthSessionStore()
    created = store.create(token_payload=_make_token_payload(), claims={"sub": "u1"}, actor_snapshot={}, audit_id="audit-1")
    fetched = store.get(created.session_id)
    assert isinstance(fetched, AuthSession)
    assert fetched.session_id == created.session_id
    assert fetched.access_token == "access-1"
    assert fetched.refresh_token == "refresh-1"
    assert fetched.id_token == "id-1"


def test_get_unknown_or_empty_returns_none() -> None:
    store = AuthSessionStore()
    assert store.get("nope") is None
    assert store.get("") is None
    assert store.get(None) is None  # type: ignore[arg-type]


def test_public_payload_excludes_tokens() -> None:
    store = AuthSessionStore()
    session = store.create(
        token_payload=_make_token_payload(),
        claims={"sub": "u1"},
        actor_snapshot={"subject": "u1", "display_name": "Alice"},
        audit_id="audit-1",
    )
    payload = session.public_payload()
    assert "access_token" not in payload
    assert "refresh_token" not in payload
    assert "id_token" not in payload
    assert payload["authenticated"] is True
    assert payload["csrf_token"] == session.csrf_token
    assert payload["actor_snapshot"]["display_name"] == "Alice"
    assert payload["audit_id"] == "audit-1"
    assert payload["development_iam_bypass"] is False


def test_update_tokens_merges_payload_and_refreshes_expiry() -> None:
    store = AuthSessionStore()
    s1 = store.create(token_payload=_make_token_payload(expires_in=10), claims={"sub": "u1"}, actor_snapshot={}, audit_id="audit-1")
    s2 = store.update_tokens(s1.session_id, token_payload={"access_token": "access-2", "expires_in": 600})
    assert s2 is not None
    assert s2.access_token == "access-2"
    # refresh_token preserved from original payload
    assert s2.refresh_token == "refresh-1"
    assert s2.expires_at > s1.expires_at


def test_update_tokens_unknown_returns_none() -> None:
    store = AuthSessionStore()
    assert store.update_tokens("nope", token_payload=_make_token_payload()) is None


def test_delete_removes_session() -> None:
    store = AuthSessionStore()
    s = store.create(token_payload=_make_token_payload(), claims={"sub": "u1"}, actor_snapshot={}, audit_id="audit-1")
    store.delete(s.session_id)
    assert store.get(s.session_id) is None


def test_expired_refresh_window_drops_session_on_get(monkeypatch: pytest.MonkeyPatch) -> None:
    store = AuthSessionStore()
    s = store.create(
        token_payload=_make_token_payload(refresh_expires_in=1),
        claims={"sub": "u1"},
        actor_snapshot={},
        audit_id="audit-1",
    )
    future = time.time() + 10
    monkeypatch.setattr("zw_brain.shared.auth_session.time.time", lambda: future)
    assert store.get(s.session_id) is None


def test_should_refresh_within_threshold() -> None:
    store = AuthSessionStore()
    # expires_in=5 places expires_at well under the 60s threshold.
    s = store.create(token_payload=_make_token_payload(expires_in=5), claims={}, actor_snapshot={}, audit_id="audit-1")
    assert AuthSessionStore.should_refresh(s) is True


def test_should_refresh_outside_threshold() -> None:
    store = AuthSessionStore()
    s = store.create(token_payload=_make_token_payload(expires_in=3600), claims={}, actor_snapshot={}, audit_id="audit-1")
    assert AuthSessionStore.should_refresh(s) is False


def test_should_refresh_requires_refresh_token() -> None:
    store = AuthSessionStore()
    s = store.create(token_payload={"access_token": "a", "expires_in": 5}, claims={}, actor_snapshot={}, audit_id="audit-1")
    # No refresh_token → cannot refresh even if within threshold.
    assert AuthSessionStore.should_refresh(s) is False


def test_development_iam_bypass_flag_round_trips() -> None:
    store = AuthSessionStore()
    s = store.create(
        token_payload=_make_token_payload(),
        claims={"sub": "dev"},
        actor_snapshot={},
        audit_id="bypass-1",
        development_iam_bypass=True,
    )
    assert s.development_iam_bypass is True
    assert s.public_payload()["development_iam_bypass"] is True


def test_clear_empties_store() -> None:
    store = AuthSessionStore()
    store.create(token_payload=_make_token_payload(), claims={}, actor_snapshot={}, audit_id="a1")
    store.create(token_payload=_make_token_payload(), claims={}, actor_snapshot={}, audit_id="a2")
    store.clear()
    # New session after clear works; clear is total.
    fresh = store.create(token_payload=_make_token_payload(), claims={}, actor_snapshot={}, audit_id="a3")
    assert store.get(fresh.session_id) is not None
