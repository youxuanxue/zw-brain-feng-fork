from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "customer_acceptance_up.sh"


def test_customer_acceptance_script_requires_real_dumps_and_datastructure() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ZW_BRAIN_LEGACY_DUMPS_DIR" in text
    assert "ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR" in text
    for schema in ["dsp_bsp", "dsp_catalog", "dsp_metaresource", "dsp_require", "dsp_handling", "dsp_example"]:
        assert schema in text
    for xml in ["dsp_catalog.xml", "dsp_metaresource.xml", "dsp_connect.xml", "dsp_handling.xml", "dsp_bsp.xml"]:
        assert xml in text


def test_customer_acceptance_script_runs_strict_migration_and_verify() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "run_acceptance_migration" in text
    assert "strict=True" in text
    assert "import_legacy_dumps.py\" verify --strict --require-zero-conflicts --json" in text
    assert "runtime smoke on imported DB with offline legacy source" in text
