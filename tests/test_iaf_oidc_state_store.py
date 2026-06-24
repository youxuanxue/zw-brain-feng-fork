"""IAF OAuth state store: peek-before-discard semantics for token exchange retries."""

from __future__ import annotations

import time

import pytest

from zw_brain.shared.iaf_oidc import IafOidcStateError, IafOidcStateStore

pytestmark = pytest.mark.no_db


def test_get_leaves_state_for_retry_until_discard() -> None:
    store = IafOidcStateStore()
    issued = store.issue(redirect_uri="http://127.0.0.1:8800/")
    peek = store.get(issued.state)
    assert peek.state == issued.state
    assert peek.nonce == issued.nonce
    # Transient token exchange failure should not burn state.
    again = store.get(issued.state)
    assert again.state == issued.state
    store.discard(issued.state)
    with pytest.raises(IafOidcStateError, match="state mismatch"):
        store.get(issued.state)


def test_consume_still_peek_and_discard() -> None:
    store = IafOidcStateStore()
    issued = store.issue()
    consumed = store.consume(issued.state)
    assert consumed.state == issued.state
    with pytest.raises(IafOidcStateError, match="state mismatch"):
        store.consume(issued.state)


def test_expired_state_removed_on_get() -> None:
    store = IafOidcStateStore(ttl_seconds=0)
    issued = store.issue()
    time.sleep(0.01)
    with pytest.raises(IafOidcStateError, match="state expired"):
        store.get(issued.state)
