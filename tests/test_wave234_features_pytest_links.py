"""F7 turn 1: wave 2/3/4 .feature 骨架 + 已知 pytest 链路门禁."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# wave-2/3 要求 ≥3 feature；wave-4 飞轮反模式 #8 拆分后仅留 1 个机械测 feature（其余 SLI 看板转 docs/customer-readiness/wave4-cutoff-criteria.md）
_WAVE_DIRS_MIN3 = (
    REPO_ROOT / ".testing" / "waves" / "wave-2-engines-b1-zones" / "features",
    REPO_ROOT / ".testing" / "waves" / "wave-3-protocol-tenant-national" / "features",
)
_WAVE_DIRS_MIN1 = (
    REPO_ROOT / ".testing" / "waves" / "wave-4-legacy-retirement" / "features",
)

# ≥5 features 已有 pytest 落地（wave-2 三引擎 + wave-0/1 横切）
_LINKED_PYTEST = (
    "tests/integration/test_approval_flow_engine.py",
    "tests/integration/test_form_schema_nl_draft.py",
    "tests/integration/test_approval_flow_nl_draft.py",
    "tests/integration/test_wave2_three_engines_acceptance.py",
    "tests/test_contract_projection.py",
    "tests/integration/test_inference_client.py",
    "tests/test_wave3_protocol_tenant.py",
)


def _scenario_count(feature_text: str) -> int:
    return len(re.findall(r"^\s*Scenario:", feature_text, flags=re.MULTILINE))


def test_wave234_each_has_at_least_three_feature_files_with_scenarios() -> None:
    for wave_dir in _WAVE_DIRS_MIN3:
        features = sorted(wave_dir.glob("*.feature"))
        assert len(features) >= 3, f"{wave_dir.name}: need ≥3 .feature files, got {len(features)}"
        with_scenarios = [f for f in features if _scenario_count(f.read_text(encoding="utf-8")) >= 1]
        assert len(with_scenarios) >= 3, f"{wave_dir.name}: need ≥3 features with Scenario blocks"
    for wave_dir in _WAVE_DIRS_MIN1:
        features = sorted(wave_dir.glob("*.feature"))
        assert len(features) >= 1, f"{wave_dir.name}: need ≥1 .feature file (Wave 4 形态学拆分后), got {len(features)}"
        with_scenarios = [f for f in features if _scenario_count(f.read_text(encoding="utf-8")) >= 1]
        assert len(with_scenarios) >= 1, f"{wave_dir.name}: need ≥1 feature with Scenario blocks"


def test_f7_linked_pytest_modules_exist_and_importable() -> None:
    missing = [rel for rel in _LINKED_PYTEST if not (REPO_ROOT / rel).is_file()]
    assert not missing, f"missing linked pytest modules: {missing}"
