"""tests/test_capability_registry_cache.py — load_manifests() 进程级缓存回归

``registered/*.json`` 是运行期只读静态资产，而 ``load_manifests`` / ``get_manifest``
处于五消费面最热路径上。本测试守住两条不变量：

1. 缓存命中——多次 ``get_manifest`` / ``load_manifests`` 只触发一次磁盘读，证明
   ``lru_cache`` 真的吃住了重复 I/O。
2. 重置路径——调用 ``load_manifests.cache_clear()`` 后再读会重新 load（磁盘读再次发生），
   证明需要热替换 manifest 的测试有明确的失效入口。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from zw_brain.capability_registry import runtime
from zw_brain.capability_registry.runtime import get_manifest, load_manifests


@pytest.fixture(autouse=True)
def _isolate_manifest_cache():
    """每个用例前后都清缓存，避免缓存状态在 session 内串味（本测试主动观测 load 次数）。"""
    load_manifests.cache_clear()
    yield
    load_manifests.cache_clear()


def _count_disk_reads(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """把 ``Path.read_text`` 包一层计数器；load_manifests 内每读一个 manifest 文件 +1。"""
    calls = {"reads": 0}
    real_read_text = Path.read_text

    def counting_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        # 只统计对 registered/*.json 的读取，避免误计无关路径。
        if self.suffix == ".json" and self.parent == runtime.REGISTRY_DIR:
            calls["reads"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    return calls


def test_load_manifests_caches_disk_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次 load 后，后续 get_manifest / load_manifests 不再触达磁盘。"""
    calls = _count_disk_reads(monkeypatch)

    first = load_manifests()
    assert first, "registry 不应为空"
    reads_after_first = calls["reads"]
    assert reads_after_first > 0, "首次 load 应至少读一个 manifest 文件"

    # 任取一个真实存在的 slug 反复读，断言不再产生磁盘读。
    sample_slug = next(iter(first))
    for _ in range(5):
        load_manifests()
        get_manifest(sample_slug)
    assert calls["reads"] == reads_after_first, (
        "缓存命中后不应再触发磁盘读，"
        f"期望 {reads_after_first}，实际 {calls['reads']}"
    )


def test_cache_clear_forces_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    """cache_clear() 后再读会重新 load——热替换 manifest 的测试据此失效缓存。"""
    calls = _count_disk_reads(monkeypatch)

    load_manifests()
    reads_after_first = calls["reads"]
    assert reads_after_first > 0

    # 不清缓存：命中，读数不变。
    load_manifests()
    assert calls["reads"] == reads_after_first

    # 清缓存：重新 load，读数翻倍（再次读全部 manifest）。
    load_manifests.cache_clear()
    load_manifests()
    assert calls["reads"] == reads_after_first * 2, (
        "cache_clear() 后应重新读取全部 manifest，"
        f"期望 {reads_after_first * 2}，实际 {calls['reads']}"
    )
