"""BFF AuthSessionStore — Redis backend + deploy guard (P0-E)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from zw_brain.shared.auth_session import (
    AuthSession,
    InMemoryAuthSessionStore,
    RedisAuthSessionStore,
    create_auth_session_store,
    validate_session_store_for_deploy,
)

pytestmark = pytest.mark.no_db


def _sample_payload() -> dict[str, Any]:
    return {
        "token_payload": {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 300, "refresh_expires_in": 3600},
        "claims": {"sub": "user-1", "preferred_username": "user1"},
        "actor_snapshot": {"subject": "user-1", "role_codes": ["ROLE_ORGAN_OPERATER"]},
        "audit_id": "audit-1",
    }


@pytest.fixture
def fake_redis():
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeRedis(decode_responses=True)


def test_auth_session_storage_roundtrip() -> None:
    session = InMemoryAuthSessionStore().create(**_sample_payload())
    restored = AuthSession.from_storage_dict(session.to_storage_dict())
    assert restored.session_id == session.session_id
    assert restored.access_token == "at-1"
    assert restored.actor_snapshot["role_codes"] == ["ROLE_ORGAN_OPERATER"]


def test_redis_store_create_get_delete(fake_redis) -> None:
    store = RedisAuthSessionStore(client=fake_redis, key_prefix="test:session:")
    created = store.create(**_sample_payload())
    loaded = store.get(created.session_id)
    assert loaded is not None
    assert loaded.csrf_token == created.csrf_token
    assert loaded.access_token == "at-1"

    store.delete(created.session_id)
    assert store.get(created.session_id) is None


def test_redis_store_shared_across_two_instances(fake_redis) -> None:
    """Simulates two REST workers reading the same BFF session."""
    store_a = RedisAuthSessionStore(client=fake_redis, key_prefix="test:session:")
    store_b = RedisAuthSessionStore(client=fake_redis, key_prefix="test:session:")
    created = store_a.create(**_sample_payload())
    shared = store_b.get(created.session_id)
    assert shared is not None
    assert shared.audit_id == "audit-1"

    updated = store_b.update_tokens(
        created.session_id,
        token_payload={"access_token": "at-2", "expires_in": 600},
    )
    assert updated is not None
    reloaded = store_a.get(created.session_id)
    assert reloaded is not None
    assert reloaded.access_token == "at-2"


def test_redis_store_update_actor_snapshot(fake_redis) -> None:
    store = RedisAuthSessionStore(client=fake_redis, key_prefix="test:session:")
    created = store.create(**_sample_payload())
    updated = store.update_actor_snapshot(created.session_id, {"subject": "user-1", "role_codes": ["ROLE_BUSIAUDIT"]})
    assert updated is not None
    assert updated.actor_snapshot["role_codes"] == ["ROLE_BUSIAUDIT"]


def test_redis_store_clear_scans_prefix(fake_redis) -> None:
    store = RedisAuthSessionStore(client=fake_redis, key_prefix="test:session:")
    s1 = store.create(**_sample_payload())
    s2 = store.create(**_sample_payload())
    assert store.get(s1.session_id) is not None
    assert store.get(s2.session_id) is not None
    store.clear()
    assert store.get(s1.session_id) is None
    assert store.get(s2.session_id) is None


def test_create_auth_session_store_defaults_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_SESSION_REDIS_URL", raising=False)
    store = create_auth_session_store()
    assert isinstance(store, InMemoryAuthSessionStore)


def test_create_auth_session_store_uses_redis_when_url_set(monkeypatch: pytest.MonkeyPatch, fake_redis) -> None:
    pytest.importorskip("redis")
    monkeypatch.setenv("ZW_BRAIN_SESSION_REDIS_URL", "redis://127.0.0.1:6379/0")

    class _FakeFromUrl:
        @staticmethod
        def from_url(url: str, *, decode_responses: bool = True):
            assert url.startswith("redis://")
            assert decode_responses is True
            return fake_redis

    import redis

    monkeypatch.setattr(redis, "from_url", _FakeFromUrl.from_url)
    store = create_auth_session_store()
    assert isinstance(store, RedisAuthSessionStore)


def test_validate_session_store_for_deploy_allows_dev_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_DEPLOY_MODE", raising=False)
    monkeypatch.delenv("ZW_BRAIN_SESSION_REDIS_URL", raising=False)
    validate_session_store_for_deploy()


def test_validate_session_store_for_deploy_requires_redis_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "prod")
    monkeypatch.delenv("ZW_BRAIN_SESSION_REDIS_URL", raising=False)
    with pytest.raises(SystemExit, match="ZW_BRAIN_SESSION_REDIS_URL"):
        validate_session_store_for_deploy()


def test_validate_session_store_for_deploy_passes_when_prod_has_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "production")
    monkeypatch.setenv("ZW_BRAIN_SESSION_REDIS_URL", "redis://redis:6379/0")
    validate_session_store_for_deploy()


def test_redis_key_uses_json_payload(fake_redis) -> None:
    store = RedisAuthSessionStore(client=fake_redis, key_prefix="test:session:")
    created = store.create(**_sample_payload())
    raw = fake_redis.get(f"test:session:{created.session_id}")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["session_id"] == created.session_id
    assert "access_token" not in created.public_payload()


def test_public_payload_includes_safe_claims_only() -> None:
    session = InMemoryAuthSessionStore().create(
        token_payload={"access_token": "secret-at", "refresh_token": "secret-rt", "expires_in": 300, "refresh_expires_in": 3600},
        claims={
            "sub": "user-1",
            "preferred_username": "zhangsan",
            "email": "zhangsan@example.com",
            "resource_access": {"zw-brain": {"roles": ["ROLE_ORGAN_OPERATER"]}},
        },
        actor_snapshot={"subject": "user-1", "current_role": "ROLE_ORGAN_OPERATER"},
        audit_id="audit-1",
    )
    public = session.public_payload()
    assert public["claims"]["preferred_username"] == "zhangsan"
    assert public["claims"]["resource_access"]["zw-brain"]["roles"] == ["ROLE_ORGAN_OPERATER"]
    assert "access_token" not in public
    assert "access_token" not in public["claims"]
