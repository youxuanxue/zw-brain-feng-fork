from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode

import jwt
from jwt.algorithms import RSAAlgorithm

from zw_brain.shared.sanitization import safe_json

DEFAULT_IAF_REALM = "picp"
DEFAULT_IAF_SSL_REQUIRED = "none"
DEFAULT_IAF_CLIENT_ID = "zw-brain"
DEFAULT_IAF_CLIENT_SECRET_ENV = "ZW_BRAIN_IAF_CLIENT_SECRET"


class IafOidcError(RuntimeError):
    pass


class IafIamConfigError(IafOidcError):
    pass


class IafOidcStateError(IafOidcError):
    pass


class IafOidcTokenError(IafOidcError):
    pass


class IafOidcTokenHealthError(IafOidcError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class IafOidcEndpoints:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    logout_endpoint: str
    jwks_uri: str
    token_healthz_endpoint: str


@dataclass(frozen=True)
class IafIamConfig:
    realm: str = DEFAULT_IAF_REALM
    auth_server_url: str = ""
    ssl_required: str = DEFAULT_IAF_SSL_REQUIRED
    client_id: str = DEFAULT_IAF_CLIENT_ID
    client_secret_env: str = field(default=DEFAULT_IAF_CLIENT_SECRET_ENV, repr=False)
    confidential_port: int = 0
    require_preferred_username: bool = True

    def __post_init__(self) -> None:
        auth_server_url = self.auth_server_url.strip().rstrip("/")
        if not auth_server_url:
            raise IafIamConfigError("ZW_BRAIN_IAF_AUTH_SERVER_URL is required")
        if not auth_server_url.startswith(("https://", "http://")):
            raise IafIamConfigError("ZW_BRAIN_IAF_AUTH_SERVER_URL must be an HTTP(S) URL")
        object.__setattr__(self, "auth_server_url", auth_server_url)

    @classmethod
    def from_env(cls) -> IafIamConfig:
        return cls(
            realm=(os.environ.get("ZW_BRAIN_IAF_REALM") or DEFAULT_IAF_REALM).strip(),
            auth_server_url=(os.environ.get("ZW_BRAIN_IAF_AUTH_SERVER_URL") or "").strip(),
            ssl_required=(os.environ.get("ZW_BRAIN_IAF_SSL_REQUIRED") or DEFAULT_IAF_SSL_REQUIRED).strip(),
            client_id=(os.environ.get("ZW_BRAIN_IAF_RESOURCE") or os.environ.get("ZW_BRAIN_IAF_CLIENT_ID") or DEFAULT_IAF_CLIENT_ID).strip(),
            client_secret_env=(os.environ.get("ZW_BRAIN_IAF_CLIENT_SECRET_ENV") or DEFAULT_IAF_CLIENT_SECRET_ENV).strip(),
        )

    @property
    def client_secret(self) -> str:
        return os.environ.get(self.client_secret_env, "")

    @property
    def endpoints(self) -> IafOidcEndpoints:
        base = self.auth_server_url
        issuer = f"{base}/realms/{self.realm}"
        openid_base = f"{issuer}/protocol/openid-connect"
        return IafOidcEndpoints(
            issuer=issuer,
            authorization_endpoint=f"{openid_base}/auth",
            token_endpoint=f"{openid_base}/token",
            logout_endpoint=f"{openid_base}/logout",
            jwks_uri=f"{openid_base}/certs",
            token_healthz_endpoint=f"{base}/v1/token-healthz",
        )

    def public_dict(self) -> dict[str, Any]:
        endpoints = self.endpoints
        return {
            "realm": self.realm,
            "auth_server_url": self.auth_server_url,
            "ssl_required": self.ssl_required,
            "resource": self.client_id,
            "confidential_port": self.confidential_port,
            "issuer": endpoints.issuer,
            "authorization_endpoint": endpoints.authorization_endpoint,
            "token_endpoint": endpoints.token_endpoint,
            "logout_endpoint": endpoints.logout_endpoint,
            "jwks_uri": endpoints.jwks_uri,
            "token_healthz_endpoint": endpoints.token_healthz_endpoint,
        }


@dataclass(frozen=True)
class IafOidcLoginState:
    state: str
    nonce: str
    issued_at: float
    redirect_uri: str | None = None
    code_verifier: str | None = None


def _new_pkce_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def pkce_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class IafOidcStateStore:
    def __init__(self, *, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._states: dict[str, IafOidcLoginState] = {}

    def issue(self, *, redirect_uri: str | None = None) -> IafOidcLoginState:
        code_verifier = _new_pkce_code_verifier()
        login_state = IafOidcLoginState(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            issued_at=time.time(),
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        self._states[login_state.state] = login_state
        return login_state

    def get(self, state: str) -> IafOidcLoginState:
        login_state = self._states.get(str(state or ""))
        if login_state is None:
            raise IafOidcStateError("state mismatch")
        if time.time() - login_state.issued_at > self._ttl_seconds:
            self._states.pop(str(state or ""), None)
            raise IafOidcStateError("state expired")
        return login_state

    def discard(self, state: str) -> None:
        self._states.pop(str(state or ""), None)

    def consume(self, state: str) -> IafOidcLoginState:
        login_state = self.get(state)
        self.discard(state)
        return login_state

    @staticmethod
    def validate_nonce(expected_nonce: str, actual_nonce: Any) -> None:
        if not expected_nonce or str(actual_nonce or "") != expected_nonce:
            raise IafOidcStateError("nonce mismatch")


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    nonce: str


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: dict[str, str] | None = None


class HttpTransport(Protocol):
    def __call__(self, request: HttpRequest) -> HttpResponse: ...


class IafOidcClient:
    def __init__(self, config: IafIamConfig | None = None) -> None:
        self.config = config or IafIamConfig.from_env()

    def authorization_request(self, *, redirect_uri: str, login_state: IafOidcLoginState, scope: str = "openid") -> AuthorizationRequest:
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "response_type": "code",
            "scope": scope,
            "state": login_state.state,
            "nonce": login_state.nonce,
        }
        if login_state.code_verifier:
            params["code_challenge"] = pkce_s256_challenge(login_state.code_verifier)
            params["code_challenge_method"] = "S256"
        return AuthorizationRequest(
            url=f"{self.config.endpoints.authorization_endpoint}?{urlencode(params)}",
            state=login_state.state,
            nonce=login_state.nonce,
        )

    def exchange_authorization_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        transport: HttpTransport,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        if not code:
            raise IafOidcError("authorization code is required")
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
        }
        if code_verifier:
            form["code_verifier"] = code_verifier
        return self._post_token_form(form, transport=transport, failure_label="token exchange")

    def refresh_access_token(self, *, refresh_token: str, transport: HttpTransport) -> dict[str, Any]:
        if not refresh_token:
            raise IafOidcError("refresh token is required")
        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
        }
        return self._post_token_form(form, transport=transport, failure_label="token refresh")

    def validate_access_token_health(self, *, authorization: str, transport: HttpTransport) -> None:
        value = str(authorization or "").strip()
        if not value.lower().startswith("bearer "):
            raise IafOidcTokenHealthError(401, "missing bearer token")
        request = HttpRequest(
            method="GET",
            url=self.config.endpoints.token_healthz_endpoint,
            headers={"Accept": "application/json", "Authorization": value},
            body=b"",
        )
        try:
            response = transport(request)
        except IafOidcError as exc:
            raise IafOidcTokenHealthError(503, "token validation service unavailable") from exc
        if response.status_code == 200:
            return
        if response.status_code == 401:
            raise IafOidcTokenHealthError(401, "token invalid or expired")
        if response.status_code == 503:
            raise IafOidcTokenHealthError(503, "token validation service unavailable")
        raise IafOidcTokenHealthError(503, f"token validation failed with HTTP {response.status_code}")

    def _post_token_form(self, form: dict[str, str], *, transport: HttpTransport, failure_label: str) -> dict[str, Any]:
        client_secret = self.config.client_secret
        if client_secret:
            form = form | {"client_secret": client_secret}
        request = HttpRequest(
            method="POST",
            url=self.config.endpoints.token_endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urlencode(form).encode("utf-8")
        )
        response = transport(request)
        if response.status_code < 200 or response.status_code >= 300:
            raise IafOidcError(f"{failure_label} failed with HTTP {response.status_code}")
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except Exception as exc:
            raise IafOidcError(f"{failure_label} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise IafOidcError(f"{failure_label} returned invalid payload")
        return payload

    def verify_id_token(self, token: str, *, jwks: dict[str, Any], expected_nonce: str | None = None) -> dict[str, Any]:
        return verify_iaf_id_token(token, config=self.config, jwks=jwks, expected_nonce=expected_nonce)


def _audience_values(claims: dict[str, Any]) -> set[str]:
    audience = claims.get("aud")
    if isinstance(audience, str):
        values = {audience}
    elif isinstance(audience, list):
        values = {str(item) for item in audience}
    else:
        values = set()
    for key in ("client_id", "clientId", "azp"):
        value = claims.get(key)
        if value:
            values.add(str(value))
    return values


def _select_jwk(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise IafOidcTokenError("invalid jwt header") from exc
    if header.get("alg") != "RS256":
        raise IafOidcTokenError("unsupported jwt algorithm")
    kid = header.get("kid")
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list) or not keys:
        raise IafOidcTokenError("jwks has no keys")
    candidates = [key for key in keys if isinstance(key, dict) and key.get("kty") == "RSA"]
    if kid:
        candidates = [key for key in candidates if key.get("kid") == kid]
    if len(candidates) != 1:
        raise IafOidcTokenError("jwks key mismatch")
    return candidates[0]


def verify_iaf_id_token(token: str, *, config: IafIamConfig, jwks: dict[str, Any], expected_nonce: str | None = None) -> dict[str, Any]:
    if not token or token.count(".") != 2:
        raise IafOidcTokenError("invalid jwt format")
    jwk = _select_jwk(token, jwks)
    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=config.endpoints.issuer,
            options={"require": ["exp", "iss", "sub"], "verify_aud": False},
        )
    except Exception as exc:
        raise IafOidcTokenError("jwt verification failed") from exc
    if not isinstance(claims, dict):
        raise IafOidcTokenError("invalid jwt claims type")
    if config.client_id not in _audience_values(claims):
        raise IafOidcTokenError("audience mismatch")
    if expected_nonce is not None:
        IafOidcStateStore.validate_nonce(expected_nonce, claims.get("nonce"))
    if not str(claims.get("sub") or ""):
        raise IafOidcTokenError("missing sub")
    if config.require_preferred_username and not str(claims.get("preferred_username") or ""):
        raise IafOidcTokenError("missing preferred_username")
    return safe_json(claims)


def verify_iaf_access_token(token: str, *, config: IafIamConfig, jwks: dict[str, Any]) -> dict[str, Any]:
    # Access tokens are signed RS256 JWTs in Keycloak; reusing id-token verification minus the nonce
    # check (access tokens carry no nonce). Calling this before trusting claims closes the gap where
    # /v1/token-healthz semantics alone cannot guarantee signature/iss/aud integrity.
    if not token or token.count(".") != 2:
        raise IafOidcTokenError("invalid jwt format")
    jwk = _select_jwk(token, jwks)
    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=config.endpoints.issuer,
            options={"require": ["exp", "iss", "sub"], "verify_aud": False},
        )
    except Exception as exc:
        raise IafOidcTokenError("jwt verification failed") from exc
    if not isinstance(claims, dict):
        raise IafOidcTokenError("invalid jwt claims type")
    if config.client_id not in _audience_values(claims):
        raise IafOidcTokenError("audience mismatch")
    if not str(claims.get("sub") or ""):
        raise IafOidcTokenError("missing sub")
    return safe_json(claims)
