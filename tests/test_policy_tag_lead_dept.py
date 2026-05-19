"""R-014 + F1/F2 fix: enforce_manifest_policy 对 tag_lead_dept 的运行时校验边缘情况.

Round-2 review 发现：原实现对 actor_tags 类型 / truthiness 不防御。
- F1: actor_tags = "string" / list / None 等非 dict 类型 → 应等同"无标签"，不能 AttributeError
- F2: tag_lead_dept = "false" / "0" / 1 等真值 fuzz → 必须严格 bool True 才算"持有标签"
"""
from __future__ import annotations

import pytest

from zw_brain.domain import policy


_MANIFEST_REQUIRING_TAG = {
    "tenant_scope": "tenant",
    "human_confirmation_required": False,
    "side_effects": True,
    "permissions": ["catalog.lead_dept_topic_review.execute"],
}


def test_actor_tags_missing_rejected():
    with pytest.raises(policy.DomainAccessDeniedError) as exc:
        policy.enforce_manifest_policy(
            skill_id="catalog.lead_dept_topic_review",
            manifest=_MANIFEST_REQUIRING_TAG,
            role="ROLE_ORGAN_MANAGER",
            payload={"role": "ROLE_ORGAN_MANAGER"},
        )
    assert "tag_lead_dept" in str(exc.value)


def test_actor_tags_none_rejected():
    with pytest.raises(policy.DomainAccessDeniedError):
        policy.enforce_manifest_policy(
            skill_id="catalog.lead_dept_topic_review",
            manifest=_MANIFEST_REQUIRING_TAG,
            role="ROLE_ORGAN_MANAGER",
            payload={"role": "ROLE_ORGAN_MANAGER", "actor_tags": None},
        )


def test_actor_tags_string_does_not_crash_and_rejected_F1():
    """F1: actor_tags 是字符串时，不能抛 AttributeError，应等同无标签."""
    with pytest.raises(policy.DomainAccessDeniedError):
        policy.enforce_manifest_policy(
            skill_id="catalog.lead_dept_topic_review",
            manifest=_MANIFEST_REQUIRING_TAG,
            role="ROLE_ORGAN_MANAGER",
            payload={"role": "ROLE_ORGAN_MANAGER", "actor_tags": "tag_lead_dept=true"},
        )


def test_actor_tags_list_does_not_crash_and_rejected_F1():
    """F1: actor_tags 是 list 时，不能抛 AttributeError，应等同无标签."""
    with pytest.raises(policy.DomainAccessDeniedError):
        policy.enforce_manifest_policy(
            skill_id="catalog.lead_dept_topic_review",
            manifest=_MANIFEST_REQUIRING_TAG,
            role="ROLE_ORGAN_MANAGER",
            payload={"role": "ROLE_ORGAN_MANAGER", "actor_tags": ["tag_lead_dept"]},
        )


def test_actor_tags_int_does_not_crash_and_rejected_F1():
    """F1: actor_tags 是 int 时，不能抛 AttributeError，应等同无标签."""
    with pytest.raises(policy.DomainAccessDeniedError):
        policy.enforce_manifest_policy(
            skill_id="catalog.lead_dept_topic_review",
            manifest=_MANIFEST_REQUIRING_TAG,
            role="ROLE_ORGAN_MANAGER",
            payload={"role": "ROLE_ORGAN_MANAGER", "actor_tags": 42},
        )


@pytest.mark.parametrize("fuzz_value", ["true", "True", "false", "0", "1", 1, 0, "", "yes"])
def test_tag_lead_dept_fuzz_truthy_strings_rejected_F2(fuzz_value):
    """F2: 字符串/数字 truthiness 模糊值都应被拒（必须严格 bool True）."""
    with pytest.raises(policy.DomainAccessDeniedError):
        policy.enforce_manifest_policy(
            skill_id="catalog.lead_dept_topic_review",
            manifest=_MANIFEST_REQUIRING_TAG,
            role="ROLE_ORGAN_MANAGER",
            payload={"role": "ROLE_ORGAN_MANAGER", "actor_tags": {"tag_lead_dept": fuzz_value}},
        )


def test_tag_lead_dept_strict_true_accepted():
    """正路径：tag_lead_dept = True 才通过."""
    policy.enforce_manifest_policy(
        skill_id="catalog.lead_dept_topic_review",
        manifest=_MANIFEST_REQUIRING_TAG,
        role="ROLE_ORGAN_MANAGER",
        payload={"role": "ROLE_ORGAN_MANAGER", "actor_tags": {"tag_lead_dept": True}},
    )


def test_non_lead_dept_permission_unaffected_by_actor_tags():
    """无关权限（不在 LEAD_DEPT_TAG_PERMISSIONS 中）不应被 tag_lead_dept 校验拦截."""
    manifest = {
        "tenant_scope": "tenant",
        "human_confirmation_required": False,
        "side_effects": True,
        "permissions": ["catalog.entry.review.execute"],  # 非 lead_dept 类
    }
    # ROLE_BUSIAUDIT 持有 catalog.entry.review.execute；不传 actor_tags 不应触发 tag 校验
    policy.enforce_manifest_policy(
        skill_id="catalog.entry.review",
        manifest=manifest,
        role="ROLE_BUSIAUDIT",
        payload={"role": "ROLE_BUSIAUDIT"},  # 无 actor_tags
    )
