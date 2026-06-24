"""IAF OAuth state store: peek-before-discard semantics for token exchange retries."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pytest

from zw_brain.shared.iaf_oidc import (
    HttpResponse,
    IafIamConfig,
    IafOidcClient,
    IafOidcStateError,
    IafOidcStateStore,
    pkce_s256_challenge,
)

pytestmark = pytest.mark.no_db


def test_get_leaves_state_for_retry_until_discard() -> None:
    store = IafOidcStateStore()
    issued = store.issue(redirect_uri="http://127.0.0.1:8800/")
    peek = store.get(issued.state)
    assert peek.state == issued.state
    assert peek.nonce == issued.nonce
    assert peek.code_verifier
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


def test_authorization_request_uses_pkce_s256() -> None:
    store = IafOidcStateStore()
    issued = store.issue(redirect_uri="http://127.0.0.1:8800/zw-brain/")
    client = IafOidcClient(IafIamConfig(auth_server_url="https://iam.example.gov/auth"))

    auth = client.authorization_request(redirect_uri=issued.redirect_uri or "", login_state=issued)
    params = parse_qs(urlparse(auth.url).query)

    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"] == [pkce_s256_challenge(issued.code_verifier or "")]
    assert params["redirect_uri"] == ["http://127.0.0.1:8800/zw-brain/"]


def test_token_exchange_sends_pkce_verifier() -> None:
    captured_body = b""

    def transport(request):
        nonlocal captured_body
        captured_body = request.body
        return HttpResponse(status_code=200, body=b'{"access_token":"a"}', headers={})

    client = IafOidcClient(IafIamConfig(auth_server_url="https://iam.example.gov/auth"))
    client.exchange_authorization_code(
        code="code-fixture",
        redirect_uri="http://127.0.0.1:8800/zw-brain/",
        transport=transport,
        code_verifier="verifier-fixture",
    )

    form = parse_qs(captured_body.decode("utf-8"))
    assert form["code_verifier"] == ["verifier-fixture"]
