"""test_signoff_from_pr.py — signoff_from_pr.py 单元测试（D46.d）.

merge workflow 本身只在 GitHub PR merge 事件触发，preflight/CI test job 跑不到它的端到端；
故核心解析+生成逻辑（scripts/signoff_from_pr.py 纯函数）由本单测兜底覆盖。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_db

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "signoff_from_pr", REPO / "scripts" / "signoff_from_pr.py"
)
sfp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sfp)


_FEATURE = ".testing/waves/wave-2-engines-b1-zones/features/engine-approval-flow.feature"


def _event(**over):
    base = {
        "number": 200,
        "merged": True,
        "merged_at": "2026-06-01T08:30:00Z",
        "html_url": "https://github.com/x/zw-brain/pull/200",
        "labels": ["signoff:e3.demo"],
        "approvers": ["alice", "bob"],
        "body": (
            "PR 正文……\n"
            "<!-- signoff\n"
            "scope: e3.demo\n"
            "kind: 双签\n"
            f"covers:\n  - {_FEATURE}\n"
            "-->\n"
            "尾部"
        ),
    }
    base.update(over)
    return base


def test_build_signoff_happy_path():
    scope, so = sfp.build_signoff(_event())
    assert scope == "e3.demo"
    assert so["signed_by"] == "alice + bob"
    assert so["date"] == "2026-06-01"
    assert so["kind"] == "双签"
    assert so["covers"] == [_FEATURE]
    assert so["decision_only"] is False
    assert "PR #200" in so["evidence"]


def test_decision_only_empty_covers():
    ev = _event(
        labels=["signoff:some-decision"],
        body="<!-- signoff\nscope: some-decision\nkind: 决策签字\ndecision_only: true\ncovers: []\n-->",
    )
    scope, so = sfp.build_signoff(ev)
    assert scope == "some-decision"
    assert so["decision_only"] is True
    assert so["covers"] == []


def test_not_merged_skips():
    assert sfp.build_signoff(_event(merged=False)) is None


def test_no_signoff_label_skips():
    assert sfp.build_signoff(_event(labels=["bug", "enhancement"])) is None


def test_missing_body_block_rejected():
    assert sfp.build_signoff(_event(body="无机读块")) is None


def test_scope_mismatch_rejected():
    ev = _event(
        labels=["signoff:e3.demo"],
        body="<!-- signoff\nscope: WRONG\nkind: 双签\ncovers:\n  - x.feature\n-->",
    )
    assert sfp.build_signoff(ev) is None


def test_bad_kind_rejected():
    ev = _event(body=f"<!-- signoff\nscope: e3.demo\nkind: 瞎签\ncovers:\n  - {_FEATURE}\n-->")
    assert sfp.build_signoff(ev) is None


def test_decision_false_but_empty_covers_rejected():
    ev = _event(body="<!-- signoff\nscope: e3.demo\nkind: 双签\ncovers: []\n-->")
    assert sfp.build_signoff(ev) is None


def test_parse_block_extracts_yaml():
    d = sfp.parse_block("a\n<!-- signoff\nscope: z\nkind: 效果验收\n-->\nb")
    assert d["scope"] == "z" and d["kind"] == "效果验收"


def test_scope_from_labels():
    assert sfp.scope_from_labels(["x", "signoff:foo.bar", "y"]) == "foo.bar"
    assert sfp.scope_from_labels(["x", "y"]) is None


def test_idempotent_existing_file(tmp_path, monkeypatch):
    # 已存在账本 → main() 判 exists 跳过不覆盖（append-only）
    import json
    out = tmp_path / "e3.demo.signoff.yaml"
    out.write_text("scope: e3.demo\n# 旧内容勿动\n", encoding="utf-8")
    ev_file = tmp_path / "ev.json"
    ev_file.write_text(json.dumps(_event()), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["signoff_from_pr.py", "--event", str(ev_file), "--out-dir", str(tmp_path)],
    )
    rc = sfp.main()
    assert rc == 0
    assert "旧内容勿动" in out.read_text(encoding="utf-8")  # 未被覆盖


def test_main_writes_new_file(tmp_path, monkeypatch):
    import json
    ev_file = tmp_path / "ev.json"
    ev_file.write_text(json.dumps(_event()), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["signoff_from_pr.py", "--event", str(ev_file), "--out-dir", str(tmp_path)],
    )
    assert sfp.main() == 0
    written = (tmp_path / "e3.demo.signoff.yaml").read_text(encoding="utf-8")
    assert "scope: e3.demo" in written and "alice + bob" in written
    assert _FEATURE in written
