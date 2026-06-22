"""Tests for scripts/check_agent_runtime_import_confinement.py (preflight 段 77 — D68 接缝守卫).

防「守卫 + 测试双双假绿」(guard+test co-vacuity)：
  - 用**真实代码里的** AgentRuntime SDK import 样本证明守卫**真命中**；
  - 用 zw-brain 封装包 import / find_spec 软探测 / 注释证明守卫**不误报**；
  - 在真实树上整体 PASS（当前接缝已收口）；
  - 在临时树上构造接缝外越界 import 证明 find_violations 真抓、且允许集真豁免。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_agent_runtime_import_confinement.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_ar_import_confinement", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 真实代码里出现过的 SDK import 形态（service.py / capability_provider.py）——守卫必须命中
_REAL_SDK_IMPORTS = [
    "from agent_runtime import RuntimeService",
    "from agent_runtime.runtime.product_config import ProductRuntimeConfig, load_product_runtime_config",
    "from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest",
    "    from agent_runtime.runtime.models import ResumeTaskRequest",  # 缩进（函数内 lazy import）
    "    from agent_runtime.runtime.dynamic_capabilities import DynamicCapabilityContext",
    "import agent_runtime",
]

# 不是 SDK import（封装包 / 软探测 / 注释）——守卫必须放过
_NON_SDK_LINES = [
    "from zw_brain.shared.agent_runtime.service import run_agent_task_sync",
    "from zw_brain.shared.agent_runtime.config import agents_dir, agent_runtime_base_url",
    '    spec = importlib.util.find_spec("agent_runtime")',
    "# 与 agent_runtime.runtime.dynamic_capabilities.DYNAMIC_PROVIDER_TOOL_CAPABILITY 一致",
    'raise RuntimeError("agent-runtime package is not installed; install offline package")',
]


def test_regex_hits_every_real_sdk_import_sample() -> None:
    """防假绿：守卫对真实 SDK import 样本逐条命中（否则守卫恒 no-op）。"""
    module = _load_module()
    for line in _REAL_SDK_IMPORTS:
        hits = module.scan_text(line)
        assert len(hits) == 1, f"应命中却漏：{line!r}"


def test_regex_misses_wrapper_softprobe_and_comment() -> None:
    """防误报：封装包 import / find_spec 软探测 / 注释 / 错误字符串均不命中。"""
    module = _load_module()
    for line in _NON_SDK_LINES:
        hits = module.scan_text(line)
        assert hits == [], f"不应命中却命中：{line!r}"


def test_real_repo_seam_is_confined() -> None:
    """真实树整体 PASS：当前 SDK import 只在接缝两文件内。"""
    module = _load_module()
    violations = module.find_violations(
        module.ZW_BRAIN, module.REPO, module.ALLOWED_SDK_IMPORTERS
    )
    assert violations == [], f"接缝外发现 SDK import：{violations}"


def test_violation_outside_seam_detected_and_allowlist_exempts(tmp_path: Path) -> None:
    """全链路真命中：接缝外文件越界 import 被抓；允许集内同样的 import 被豁免。"""
    module = _load_module()
    allowed = frozenset({"zw_brain/shared/agent_runtime/service.py"})

    # 接缝外：zw_brain/command/foo.py 直接 import SDK → 必被抓
    outside = tmp_path / "zw_brain" / "command" / "foo.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("from agent_runtime import RuntimeService\n", encoding="utf-8")

    # 接缝内（允许集）：同样的 import → 必被豁免
    inside = tmp_path / "zw_brain" / "shared" / "agent_runtime" / "service.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("from agent_runtime import RuntimeService\n", encoding="utf-8")

    violations = module.find_violations(tmp_path / "zw_brain", tmp_path, allowed)
    rels = {rel for rel, _lineno, _line in violations}
    assert "zw_brain/command/foo.py" in rels, "接缝外越界 import 应被抓"
    assert "zw_brain/shared/agent_runtime/service.py" not in rels, "允许集内应豁免"


def test_main_returns_zero_on_real_repo() -> None:
    """守卫 main() 在真实树返回 0（与 preflight 段 77 行为一致）。"""
    module = _load_module()
    assert module.main() == 0
