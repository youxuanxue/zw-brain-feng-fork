from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from zw_brain.shared.iaf_oidc import (
    DEFAULT_IAF_CLIENT_SECRET_ENV,
    IafIamConfig,
    IafIamConfigError,
    IafOidcClient,
    IafOidcError,
    IafOidcStateError,
    IafOidcStateStore,
    IafOidcTokenError,
    verify_iaf_id_token,
)
from zw_brain.shared.runtime_config import get_iaf_iam_public_config


class _KeyFixture:
    def __init__(self, kid: str = "test-key") -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        self.jwks = {"keys": [public_jwk]}
        self.kid = kid

    def encode(self, claims: dict[str, Any], *, key: Any | None = None, kid: str | None = None, alg: str = "RS256") -> str:
        return jwt.encode(claims, key or self.private_key, algorithm=alg, headers={"kid": kid or self.kid, "typ": "JWT"})


def _config() -> IafIamConfig:
    return IafIamConfig(realm="picp", auth_server_url="https://iaf.example/auth", client_id="zw-brain")


def _claims(config: IafIamConfig, **overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": config.endpoints.issuer,
        "aud": [config.client_id],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
        "sub": "iaf-user-001",
        "nonce": "nonce-001",
        "preferred_username": "zhangsan",
        "phone": "13800001111",
        "email": "zhangsan@sd.gov.cn",
        "realm_access": {"roles": ["ACCOUNT_ADMIN"]},
        "resource_access": {"zw-brain": {"roles": ["r7"]}},
    }
    claims.update(overrides)
    return claims


def test_iaf_config_from_env_requires_injected_auth_server_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_IAF_AUTH_SERVER_URL", raising=False)

    with pytest.raises(IafIamConfigError) as excinfo:
        IafIamConfig.from_env()

    message = str(excinfo.value)
    assert "ZW_BRAIN_IAF_AUTH_SERVER_URL is required" in message
    assert "cnp-jn-rgzn-inlinux-test" not in message


def test_iaf_config_derives_keycloak_oidc_endpoints_and_public_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DEFAULT_IAF_CLIENT_SECRET_ENV, raising=False)
    config = _config()

    assert config.endpoints.issuer == "https://iaf.example/auth/realms/picp"
    assert config.endpoints.authorization_endpoint == "https://iaf.example/auth/realms/picp/protocol/openid-connect/auth"
    assert config.endpoints.token_endpoint == "https://iaf.example/auth/realms/picp/protocol/openid-connect/token"
    assert config.endpoints.logout_endpoint == "https://iaf.example/auth/realms/picp/protocol/openid-connect/logout"
    assert config.endpoints.jwks_uri == "https://iaf.example/auth/realms/picp/protocol/openid-connect/certs"
    public = config.public_dict()
    assert public["resource"] == "zw-brain"
    assert public["credential_env"] == DEFAULT_IAF_CLIENT_SECRET_ENV
    assert "credentials" not in public
    assert config.client_secret == ""


def test_runtime_config_reads_iaf_env_without_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_IAF_REALM", "picp")
    monkeypatch.setenv("ZW_BRAIN_IAF_AUTH_SERVER_URL", "https://iaf.example/auth/")
    monkeypatch.setenv("ZW_BRAIN_IAF_SSL_REQUIRED", "none")
    monkeypatch.setenv("ZW_BRAIN_IAF_CLIENT_ID", "zw-brain")
    monkeypatch.setenv(DEFAULT_IAF_CLIENT_SECRET_ENV, "super-secret")

    public = get_iaf_iam_public_config()

    assert public["realm"] == "picp"
    assert public["ssl_required"] == "none"
    assert public["resource"] == "zw-brain"
    assert "super-secret" not in json.dumps(public)


def test_state_store_issues_consumes_once_and_validates_nonce() -> None:
    store = IafOidcStateStore(ttl_seconds=60)
    state = store.issue(redirect_uri="https://brain.example/callback")

    assert len(state.state) >= 32
    assert len(state.nonce) >= 32
    assert store.consume(state.state) == state
    with pytest.raises(IafOidcStateError, match="state mismatch"):
        store.consume(state.state)
    IafOidcStateStore.validate_nonce(state.nonce, state.nonce)
    with pytest.raises(IafOidcStateError, match="nonce mismatch"):
        IafOidcStateStore.validate_nonce(state.nonce, "bad")


def test_authorization_request_contains_state_nonce_and_client() -> None:
    config = _config()
    state = IafOidcStateStore().issue()
    request = IafOidcClient(config).authorization_request(redirect_uri="https://brain.example/callback", login_state=state)
    params = parse_qs(request.url.split("?", 1)[1])

    assert request.url.startswith(config.endpoints.authorization_endpoint)
    assert params["client_id"] == ["zw-brain"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == ["https://brain.example/callback"]
    assert params["state"] == [state.state]
    assert params["nonce"] == [state.nonce]
    assert params["scope"] == ["openid profile email"]


def test_token_exchange_uses_injected_transport_and_keeps_secret_out_of_result(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv(DEFAULT_IAF_CLIENT_SECRET_ENV, "exchange-secret")
    client = IafOidcClient(_config())

    def transport(request):  # type: ignore[no-untyped-def]
        captured["method"] = request.method
        captured["url"] = request.url
        captured["body"] = request.body.decode("utf-8")
        return type("Response", (), {"status_code": 200, "body": b'{"id_token":"id.jwt","token_type":"Bearer"}'})()

    result = client.exchange_authorization_code(code="auth-code", redirect_uri="https://brain.example/callback", transport=transport)

    assert captured["method"] == "POST"
    assert captured["url"] == client.config.endpoints.token_endpoint
    form = parse_qs(captured["body"])
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["auth-code"]
    assert form["redirect_uri"] == ["https://brain.example/callback"]
    assert form["client_id"] == ["zw-brain"]
    assert form["client_secret"] == ["exchange-secret"]
    assert result == {"id_token": "id.jwt", "token_type": "Bearer"}
    assert "exchange-secret" not in json.dumps(result)


def test_token_exchange_rejects_http_error_without_body_leak() -> None:
    client = IafOidcClient(_config())

    def transport(_request):  # type: ignore[no-untyped-def]
        return type("Response", (), {"status_code": 401, "body": b'{"error":"invalid_client","client_secret":"leak"}'})()

    with pytest.raises(IafOidcError) as excinfo:
        client.exchange_authorization_code(code="auth-code", redirect_uri="https://brain.example/callback", transport=transport)
    assert "client_secret" not in str(excinfo.value)
    assert "leak" not in str(excinfo.value)


def test_verify_iaf_id_token_accepts_valid_rs256_jwks_claims() -> None:
    config = _config()
    keys = _KeyFixture()
    token = keys.encode(_claims(config))

    claims = verify_iaf_id_token(token, config=config, jwks=keys.jwks, expected_nonce="nonce-001")

    assert claims["sub"] == "iaf-user-001"
    assert claims["preferred_username"] == "zhangsan"
    assert claims["aud"] == ["zw-brain"]
    assert claims["phone"] == "13800001111"


def test_verify_iaf_id_token_accepts_client_id_when_audience_is_absent() -> None:
    config = _config()
    keys = _KeyFixture()
    claims = _claims(config, client_id="zw-brain")
    claims.pop("aud")
    token = keys.encode(claims)

    verified = verify_iaf_id_token(token, config=config, jwks=keys.jwks, expected_nonce="nonce-001")

    assert verified["client_id"] == "zw-brain"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"iss": "https://iaf.example/auth/realms/other"}, "jwt verification failed"),
        ({"aud": ["other-client"]}, "audience mismatch"),
        ({"exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())}, "jwt verification failed"),
        ({"nonce": "bad"}, "nonce mismatch"),
        ({"sub": ""}, "missing sub"),
        ({"preferred_username": ""}, "missing preferred_username"),
    ],
)
def test_verify_iaf_id_token_rejects_invalid_claim_boundaries(override: dict[str, Any], message: str) -> None:
    config = _config()
    keys = _KeyFixture()
    token = keys.encode(_claims(config, **override))

    with pytest.raises((IafOidcTokenError, IafOidcStateError), match=message):
        verify_iaf_id_token(token, config=config, jwks=keys.jwks, expected_nonce="nonce-001")


def test_verify_iaf_id_token_rejects_signature_mismatch() -> None:
    config = _config()
    good_keys = _KeyFixture(kid="same-kid")
    bad_keys = _KeyFixture(kid="same-kid")
    token = good_keys.encode(_claims(config))

    with pytest.raises(IafOidcTokenError, match="jwt verification failed"):
        verify_iaf_id_token(token, config=config, jwks=bad_keys.jwks, expected_nonce="nonce-001")


def test_verify_iaf_id_token_rejects_unsigned_jwt() -> None:
    config = _config()
    token = jwt.encode(_claims(config), key=None, algorithm="none", headers={"typ": "JWT"})

    with pytest.raises(IafOidcTokenError, match="unsupported jwt algorithm"):
        verify_iaf_id_token(token, config=config, jwks={"keys": [{"kty": "RSA"}]}, expected_nonce="nonce-001")
