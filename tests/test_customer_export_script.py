"""Contract + redaction-correctness tests for the M0 export pipeline.

Covers `scripts/_export_redaction_rules.py` (rule loading, decisions),
`scripts/customer_export.py` (postprocess + bundle + verify), and the
`scripts/customer_export.sh` shell entry as plain text contract.

Live mysqldump is not exercised — that requires a real MySQL host, which the
CI sandbox does not have. Dry-run mode against `old/10示例数据/` is the
intended customer-rehearsal path and gives full coverage of the in-repo code.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT_SH = REPO / "scripts" / "customer_export.sh"
SCRIPT_PY = REPO / "scripts" / "customer_export.py"
RULES_PY = REPO / "scripts" / "_export_redaction_rules.py"
SAMPLE_DUMPS = REPO / "old" / "10示例数据"
DATASTRUCTURE = REPO / "old" / "12-datastructure"

# `old/` is .gitignored — the legacy customer dumps + datastructure XMLs only
# exist on engineer workstations and customer-site rehearsals. On clean CI
# checkouts these tests get skipped; the pure-Python redaction unit tests
# below still run and cover the rule engine.
requires_sample_dumps = pytest.mark.skipif(
    not SAMPLE_DUMPS.is_dir() or not any(SAMPLE_DUMPS.glob("dump-*.sql")),
    reason="old/10示例数据/ not present (gitignored; rehearsal-only)",
)
requires_datastructure = pytest.mark.skipif(
    not DATASTRUCTURE.is_dir() or not any(DATASTRUCTURE.glob("*.xml")),
    reason="old/12-datastructure/ not present (gitignored; rehearsal-only)",
)

sys.path.insert(0, str(REPO))

from scripts._export_redaction_rules import (  # noqa: E402
    RedactionConfig,
    RedactionDecision,
    load_redaction_config,
    mask_value,
)


@requires_datastructure
def test_redaction_rules_load_from_real_xml() -> None:
    """Loading XML schemas should yield at least one rule per known schema."""
    config = load_redaction_config(DATASTRUCTURE)
    assert isinstance(config, RedactionConfig)
    schemas = set(config.rules.keys())
    # The XML files in old/12-datastructure cover all 17 legacy schemas.
    for must_have in ("dsp_catalog", "dsp_metaresource", "dsp_handling", "dsp_bsp"):
        assert must_have in schemas, f"missing redaction rules for schema: {must_have}"


def test_redaction_rules_flag_known_pii_via_pattern_fallback() -> None:
    """Hard-coded PII patterns should still fire even when XML stays silent."""
    config = RedactionConfig()
    assert config.decide("anything", "any_table", "user_phone").redact
    assert config.decide("anything", "any_table", "id_card_no").redact
    assert config.decide("anything", "any_table", "creator_email").redact
    assert config.decide("anything", "any_table", "app_secret").redact
    assert config.decide("anything", "any_table", "home_address").redact
    # Innocuous columns should NOT be flagged.
    assert not config.decide("anything", "any_table", "name_cn").redact
    assert not config.decide("anything", "any_table", "create_time").redact


def test_mask_value_replaces_strings_and_zeros_numeric_hint() -> None:
    decision = RedactionDecision(redact=True, kind="phone")
    # String column gets typed placeholder
    assert mask_value("mobile_phone", "13800001111", decision) == "<REDACTED:PHONE>"
    # Numeric-hint column gets `0`
    assert mask_value("phone_no", "13800001111", decision) == 0
    # NULL passes through
    assert mask_value("mobile_phone", None, decision) is None
    # Non-redact decision returns original
    keep = RedactionDecision(redact=False)
    assert mask_value("mobile_phone", "keepme", keep) == "keepme"


@requires_sample_dumps
def test_postprocess_one_dump_redacts_and_emits_crc(tmp_path: Path) -> None:
    """Round-trip one small real dump through postprocess; verify CRC + redaction."""
    src_candidates = list(SAMPLE_DUMPS.glob("dump-dsp_basesubject-*.sql"))
    assert src_candidates, "expected at least one dsp_basesubject dump in old/10示例数据/"
    src = src_candidates[0]
    out = tmp_path / src.name
    code = subprocess.run(
        [sys.executable, str(SCRIPT_PY), "postprocess", "--input", str(src), "--output", str(out)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert code.returncode == 0, code.stderr
    report = json.loads(code.stdout.strip().splitlines()[-1])
    assert report["filename"] == src.name
    assert report["schema"] == "dsp_basesubject"
    assert report["rowcount"] > 0
    assert len(report["crc32"]) == 8
    assert len(report["sha256"]) == 64
    # CRC + rowcount sidecar files must exist
    assert (out.parent / (out.name + ".crc")).exists()
    assert (out.parent / (out.name + ".rowcount")).exists()


@pytest.mark.slow_infra
@requires_sample_dumps
@requires_datastructure
def test_bundle_full_directory_creates_manifest(tmp_path: Path) -> None:
    """Bundle all 17 sample dumps; manifest.json must list every file and sum rows."""
    out_dir = tmp_path / "B-test-001"
    code = subprocess.run(
        [
            sys.executable, str(SCRIPT_PY), "bundle",
            "--input-dir", str(SAMPLE_DUMPS),
            "--output-dir", str(out_dir),
            "--batch-id", "B-test-001",
            "--tenant-id", "sd-default",
            "--datastructure-dir", str(DATASTRUCTURE),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert code.returncode == 0, code.stderr
    manifest_path = out_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["batch_id"] == "B-test-001"
    assert manifest["tenant_id"] == "sd-default"
    assert manifest["file_count"] == 17  # 16 dsp_* + 1 data_resource
    assert manifest["total_rows"] > 0
    # Redaction must hit at least the four major kinds in real Shandong data.
    summary = manifest["redaction_summary"]
    for kind in ("phone", "email", "addr"):
        assert summary.get(kind, 0) > 0, f"expected redactions of kind={kind} in sd-default data"


@requires_sample_dumps
def test_bundle_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    out_dir = tmp_path / "B-already-there"
    out_dir.mkdir()
    (out_dir / "stale.txt").write_text("old", encoding="utf-8")
    code = subprocess.run(
        [
            sys.executable, str(SCRIPT_PY), "bundle",
            "--input-dir", str(SAMPLE_DUMPS),
            "--output-dir", str(out_dir),
            "--batch-id", "B-already-there",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert code.returncode == 2
    assert "non-empty" in code.stderr


@pytest.mark.slow_infra
@requires_sample_dumps
def test_verify_reports_ok_on_fresh_bundle(tmp_path: Path) -> None:
    out_dir = tmp_path / "B-verify-ok"
    subprocess.run(
        [
            sys.executable, str(SCRIPT_PY), "bundle",
            "--input-dir", str(SAMPLE_DUMPS),
            "--output-dir", str(out_dir),
            "--batch-id", "B-verify-ok",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    code = subprocess.run(
        [sys.executable, str(SCRIPT_PY), "verify", "--batch-dir", str(out_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert code.returncode == 0
    report = json.loads(code.stdout.strip().splitlines()[-1])
    assert report["ok"] is True
    assert report["failures"] == []


@pytest.mark.slow_infra
@requires_sample_dumps
def test_verify_detects_tampered_file(tmp_path: Path) -> None:
    out_dir = tmp_path / "B-tampered"
    subprocess.run(
        [
            sys.executable, str(SCRIPT_PY), "bundle",
            "--input-dir", str(SAMPLE_DUMPS),
            "--output-dir", str(out_dir),
            "--batch-id", "B-tampered",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    # Pick the smallest emitted dump file to keep the tamper cheap.
    dumps = sorted((out_dir / f for f in os.listdir(out_dir) if f.startswith("dump-") and f.endswith(".sql")), key=lambda p: p.stat().st_size)
    assert dumps
    victim = dumps[0]
    with victim.open("a", encoding="utf-8") as fh:
        fh.write("-- tampered\n")
    code = subprocess.run(
        [sys.executable, str(SCRIPT_PY), "verify", "--batch-dir", str(out_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert code.returncode == 1
    report = json.loads(code.stdout.strip().splitlines()[-1])
    assert report["ok"] is False
    assert any(victim.name in failure for failure in report["failures"])


@pytest.mark.slow_infra
@requires_sample_dumps
def test_shell_entry_dry_run_with_sample_dumps(tmp_path: Path) -> None:
    """Smoke-test the bash entry script in --from-dir dry-run mode end-to-end."""
    if shutil.which("bash") is None:
        return  # CI without bash: redaction Python code is covered above.
    out_dir = tmp_path / "B-shell-001"
    code = subprocess.run(
        [
            "bash", str(SCRIPT_SH),
            f"--from-dir={SAMPLE_DUMPS}",
            f"--output-dir={out_dir}",
            "--batch-id=B-shell-001",
            "--tenant=sd-default",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert code.returncode == 0, code.stderr
    assert (out_dir / "manifest.json").is_file()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tenant_id"] == "sd-default"
    assert manifest["file_count"] >= 1
