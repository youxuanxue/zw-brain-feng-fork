"""Public IAF configuration exposure guardrails."""

from __future__ import annotations

from zw_brain.shared.iaf_oidc import IafIamConfig


def test_iaf_public_config_omits_client_secret_env_name() -> None:
    cfg = IafIamConfig(auth_server_url="https://iam.example.gov", realm="picp")

    public = cfg.public_dict()

    assert "credential_env" not in public
    assert "client_secret" not in public
