"""tests/test_capability_boundary.py — preflight 段 22 自动化回归

Verifies scripts/check_capability_boundary.py (P0-05 永久门禁) 的核心行为：
- builtin live 落在 §1.3 已知禁区前缀 → exit 1 (FAIL)
- 全部合规 → exit 0 (ok)
- external_capability binding 在同域 → exit 0 (合法形态，对应 §1.3 "桥接外部消费 ≠ 自建")

替代原 P0-05 的手动 mutate-restore log（.data/customer-acceptance/p0-05-negative-test.log），
让"装边界"的命题本身也被自动化 test 守住。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_capability_boundary.py"


def _write_manifest(directory: Path, skill_id: str, *, binding: str, status: str, journey: str = "j1") -> None:
    """Write a minimal manifest the check script can parse. Fields kept minimal — only
    skill_id / execution_binding / product_scope are consumed by check_capability_boundary."""
    manifest = {
        "skill_id": skill_id,
        "execution_binding": binding,
        "product_scope": {"journey": journey, "status": status},
    }
    (directory / f"{skill_id}.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _run_check(manifest_dir: Path) -> tuple[int, str]:
    """Run check_capability_boundary.py with REGISTERED pointed at tmp dir via env override.

    The script reads REGISTERED as a module-level constant; we re-import it under a patched
    path by running the script as a subprocess with a small wrapper that monkey-patches the
    constant before main() runs. Subprocess keeps each test fully isolated.
    """
    wrapper = (
        "import sys, pathlib\n"
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('cb', r'{SCRIPT}')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"mod.REGISTERED = pathlib.Path(r'{manifest_dir}')\n"
        "sys.exit(mod.main())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", wrapper],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def test_compliant_registry_passes(tmp_path: Path) -> None:
    """全合规 registry：核心 journey live+builtin + 禁区前缀但已 external → exit 0。"""
    _write_manifest(tmp_path, "data.search", binding="builtin", status="live", journey="j1")
    _write_manifest(tmp_path, "catalog.entry.publish", binding="builtin", status="live", journey="j2")
    _write_manifest(tmp_path, "metadata.lineage.query", binding="builtin", status="external", journey="external")
    _write_manifest(tmp_path, "adapter.national.catalog.pull", binding="builtin", status="deferred:wave-3", journey="national")

    code, out = _run_check(tmp_path)
    assert code == 0, f"expected exit 0, got {code}; output:\n{out}"
    assert "0 live+builtin violations" in out


def test_forbidden_zone_live_builtin_fails(tmp_path: Path) -> None:
    """禁区前缀 + status=live + binding=builtin → exit 1 (回潮检测)。"""
    _write_manifest(tmp_path, "data.search", binding="builtin", status="live", journey="j1")
    # 故意越界：metadata.lineage.* 是 §1.3 血缘禁区，不允许 live+builtin
    _write_manifest(tmp_path, "metadata.lineage.upsert", binding="builtin", status="live", journey="j1")

    code, out = _run_check(tmp_path)
    assert code == 1, f"expected exit 1, got {code}; output:\n{out}"
    assert "metadata.lineage.upsert" in out
    assert "§1.3 血缘" in out


def test_external_capability_in_forbidden_zone_passes(tmp_path: Path) -> None:
    """关键 positive case：禁区前缀 + binding=external_capability → 不应触发段 22。

    这对应 §1.3 设计 intent："禁的是主 zw-brain 自建 builtin，不是通过外部能力桥接消费"。
    external.lineage.graph.build / external.quality.scan.execute 等就是这种合法形态。
    """
    # binding=external_capability + status=external，即使 skill_id 在 §1.3 禁区，也应通过
    _write_manifest(tmp_path, "external.lineage.graph.build", binding="external_capability", status="external", journey="external")
    _write_manifest(tmp_path, "external.quality.scan.execute", binding="external_capability", status="external", journey="external")
    _write_manifest(tmp_path, "external.notification.workorder.dispatch", binding="external_capability", status="external", journey="external")

    code, out = _run_check(tmp_path)
    assert code == 0, f"expected exit 0 (external bridge is legal), got {code}; output:\n{out}"
    assert "0 live+builtin violations" in out


def test_multiple_violations_all_reported(tmp_path: Path) -> None:
    """多条越界一次性全报，不在第一条就 return（便于 reviewer 一次看完）。"""
    _write_manifest(tmp_path, "metadata.lineage.query", binding="builtin", status="live", journey="j1")
    _write_manifest(tmp_path, "quality.task.run", binding="builtin", status="live", journey="j1")
    _write_manifest(tmp_path, "standard.asset.sync", binding="builtin", status="live", journey="j1")

    code, out = _run_check(tmp_path)
    assert code == 1
    assert "3 live+builtin violation(s)" in out
    for sid in ("metadata.lineage.query", "quality.task.run", "standard.asset.sync"):
        assert sid in out, f"violation {sid} not reported in output:\n{out}"


def test_empty_registry_passes(tmp_path: Path) -> None:
    """空 registry 不应崩，应正常 exit 0（启动期 / CI cold start 兜底）。"""
    code, out = _run_check(tmp_path)
    assert code == 0
    assert "0 live+builtin violations" in out


def test_classify_zone_known_prefixes() -> None:
    """直接 import classify_zone，覆盖 7 类禁区前缀分类正确性（防 FORBIDDEN_ZONES 误改）。"""
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("cb", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        cases = {
            "metadata.lineage.query": "§1.3 血缘",
            "quality.task.run": "§1.3 质量",
            "ops.catalog.quality.upsert": "§1.3 质量",
            "ops.gateway.heartbeat.ingest": "§1.3 运维监控",
            "ops.shift_handover.submit": "§1.3 运维监控",
            "ops.exchange.diagnose": "§1.3 运维监控",
            "ops.ticket.create": "§1.3 工单（外部消息中心）",
            "adapter.national.catalog.pull": "§1.3 国家通道",
            "direct_access.catalog.query": "§1.3 国家直达",
            "standard.asset.sync": "§1.3 标准服务",
            # 非禁区：必须返回 None
            "data.search": None,
            "catalog.entry.publish": None,
            "application.grant.approve": None,
        }
        for sid, expected in cases.items():
            assert mod.classify_zone(sid) == expected, f"{sid} 预期 {expected}, 实得 {mod.classify_zone(sid)}"
    finally:
        sys.path.pop(0)


def test_catalog_national_ext_elem_compile_promoted_via_d50() -> None:
    """D50 / C5b：国家扩展要素目录编制 compile 能力已正式立项 live（journey=j2，非禁区）。

    原 F5「deferred:wave-3 占位防回潮」断言随 D50 立项反转为正向就绪态守卫：
      1. manifest 字段 product_scope.status == 'live'（builtin binding，j2 子旅程）；
      2. DISPATCH_TABLE 中有 catalog.national_ext_elem.compile（已 wire 到 brain runtime）；
      3. _CATEGORIZATION.md 中有对应行（live 进 4 桶清单）；
      4. 编制状态机独立 data_catalog 主线（由 test_national_ext_elem_walker 等守）。

    注：catalog.national_ext_elem.compile 是 §1.3 之外的合法 builtin live 能力（j2 catalog
    编制态，非国家通道出站）；国家平台出站仍收口到 escalate(j1)/compile(j2) handler 经
    national_channel_gate + NationalDirectClient（见 D50 §二）。任一条退化即回潮。
    """
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "zw_brain" / "capability_registry" / "registered" / "catalog.national_ext_elem.compile.json"
    dispatch_path = repo_root / "zw_brain" / "command" / "dispatch.py"
    categorization_path = repo_root / "zw_brain" / "command" / "handlers" / "_CATEGORIZATION.md"

    assert manifest_path.exists(), f"D50 manifest 缺失：{manifest_path}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["slug"] == "catalog.national_ext_elem.compile"
    scope = manifest.get("product_scope") or {}
    assert scope.get("journey") == "j2", scope
    assert scope.get("status") == "live", scope

    dispatch_text = dispatch_path.read_text(encoding="utf-8")
    assert "catalog.national_ext_elem.compile" in dispatch_text, (
        "D50 立项：live compile 能力应在 DISPATCH_TABLE / dispatch.py 中 wire"
    )

    categorization_text = categorization_path.read_text(encoding="utf-8")
    assert "catalog.national_ext_elem.compile" in categorization_text, (
        "D50 立项：live compile 能力应在 _CATEGORIZATION.md 4 桶清单中登记"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
