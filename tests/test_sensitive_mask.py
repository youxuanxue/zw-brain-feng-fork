"""Unit + integration tests for the read-side sensitive field mask layer."""
from __future__ import annotations

from zw_brain.shared.sensitive_mask import (
    apply_field_masks,
    mask_address,
    mask_email,
    mask_id_card,
    mask_name,
    mask_phone,
    mask_value,
)

# ---------------------------------------------------------------------------
# Atomic mask functions
# ---------------------------------------------------------------------------

def test_mask_phone_external_keeps_first3_last4() -> None:
    assert mask_phone("13800001111") == "138****1111"
    assert mask_phone("13800001111", role="external") == "138****1111"
    # internal_admin = full
    assert mask_phone("13800001111", role="internal_admin") == "13800001111"
    # internal_viewer same as external for phone (level 1)
    assert mask_phone("13800001111", role="internal_viewer") == "138****1111"


def test_mask_phone_handles_short_or_non_numeric() -> None:
    assert mask_phone("123") == "12***"
    assert mask_phone("12") == "***"
    assert mask_phone("") == ""
    assert mask_phone(None) is None
    # bytes-like input — return unchanged
    assert mask_phone(13800001111) == 13800001111  # type: ignore[arg-type]


def test_mask_name_chinese_and_latin() -> None:
    assert mask_name("张三") == "张*"
    assert mask_name("欧阳锋") == "欧**"
    assert mask_name("张") == "张*"  # single char — pad with *
    assert mask_name("Alice") == "A****"
    assert mask_name("a") == "a*"
    assert mask_name("张三", role="internal_admin") == "张三"


def test_mask_email_levels() -> None:
    # default = external (level 2 for email — host hidden)
    assert mask_email("alice@sd.gov.cn") == "a***@***"
    assert mask_email("alice@sd.gov.cn", role="internal_viewer") == "a***@sd.gov.cn"
    assert mask_email("alice@sd.gov.cn", role="internal_admin") == "alice@sd.gov.cn"
    # malformed: pass through
    assert mask_email("not-an-email") == "not-an-email"
    assert mask_email("@x") == "*@***"


def test_mask_id_card_levels() -> None:
    full = "370101199001011234"
    assert mask_id_card(full, role="internal_admin") == full
    assert mask_id_card(full, role="internal_viewer") == "370" + "*" * 11 + "1234"
    assert mask_id_card(full, role="external") == "*" * 18
    assert mask_id_card("123") == "*" * 3


def test_mask_address_levels() -> None:
    # Address is treated as strong-mask-by-default; even internal_viewer sees just `***`.
    addr = "山东省济南市历下区某路 88 号"
    assert mask_address(addr, role="internal_admin") == addr
    assert mask_address(addr, role="internal_viewer") == "***"
    assert mask_address(addr, role="external") == "***"


def test_mask_value_dispatch() -> None:
    assert mask_value("13800001111", "phone") == "138****1111"
    assert mask_value("张三", "name") == "张*"
    # unknown kind: pass through
    assert mask_value("payload", "unknown_kind") == "payload"


# ---------------------------------------------------------------------------
# apply_field_masks — recursive walk
# ---------------------------------------------------------------------------

def test_apply_field_masks_recurses_dict_and_keys_off_field_name() -> None:
    payload = {
        "display_name": "高大量",
        "phone": "13800001111",
        "email": "high@sd.gov.cn",
        "address": "山东省济南市历下区某街 1 号",
        "identity_num": "370101199001011234",
        "org_code": "11370000MB284651XL",  # not sensitive — no mask
        "nested": {
            "contact": {"contact_name": "李四", "contact_phone": "13900002222"},
            "items": [{"name": "王五", "phone": "13700003333"}, {"name": "赵六"}],
        },
    }
    masked = apply_field_masks(payload, role="internal_viewer")
    assert masked["display_name"] == "高**"
    assert masked["phone"] == "138****1111"
    assert masked["email"] == "h***@sd.gov.cn"
    assert masked["address"] == "***"  # internal_viewer still strong-masks address
    assert masked["identity_num"] == "370" + "*" * 11 + "1234"
    assert masked["org_code"] == "11370000MB284651XL"  # unchanged
    assert masked["nested"]["contact"]["contact_name"] == "李*"
    assert masked["nested"]["contact"]["contact_phone"] == "139****2222"
    assert masked["nested"]["items"][0]["name"] == "王*"
    assert masked["nested"]["items"][0]["phone"] == "137****3333"
    assert masked["nested"]["items"][1]["name"] == "赵*"


def test_apply_field_masks_internal_admin_is_passthrough() -> None:
    payload = {"phone": "13800001111", "name": "张三"}
    assert apply_field_masks(payload, role="internal_admin") == payload


def test_apply_field_masks_field_policy_overrides_default() -> None:
    payload = {"phone": "13800001111", "label": "营业执照"}
    # opt 'label' INTO masking as a name; opt 'phone' OUT (empty string)
    masked = apply_field_masks(
        payload,
        role="internal_viewer",
        field_policy={"label": "name", "phone": ""},
    )
    assert masked["phone"] == "13800001111"  # opted out
    assert masked["label"] == "营***"  # opted in (Chinese text → mask)


def test_apply_field_masks_default_role_is_external_safest() -> None:
    payload = {"phone": "13800001111", "email": "x@y.cn"}
    masked = apply_field_masks(payload)
    assert masked["phone"] == "138****1111"
    # external role hides host
    assert masked["email"] == "x***@***"


def test_apply_field_masks_handles_non_string_values() -> None:
    payload = {"phone": None, "name": 42, "items": [None, 1, "张三"]}
    masked = apply_field_masks(payload, role="external")
    assert masked["phone"] is None
    assert masked["name"] == 42
    # items list inherits parent_key='items' which is not a mask-hint, so strings pass through
    assert masked["items"] == [None, 1, "张三"]


# ---------------------------------------------------------------------------
# Integration: real ActorProjection record's profile_json end-to-end
# ---------------------------------------------------------------------------

def test_apply_field_masks_against_actor_profile_shape() -> None:
    # Mirrors the shape produced by zw_brain/adapters/legacy/mappers/governance.py
    actor_profile = {
        "account": "zhangsan",
        "phone": "13800001111",
        "mobile": "13800001112",
        "email": "zhangsan@sd.gov.cn",
        "identity_num": "370101199001011234",
        "address": "山东省济南市历下区某街 1 号",
        "region_code": "370100",
        "region_name": "济南市",
        "org_name": "省大数据局",
        "user_type": "0",
        "is_admin": 0,
    }
    safe = apply_field_masks(actor_profile, role="external")
    # masked
    assert safe["phone"] == "138****1111"
    assert safe["mobile"] == "138****1112"
    assert safe["email"] == "z***@***"
    assert safe["identity_num"] == "*" * 18
    assert safe["address"] == "***"
    # untouched
    assert safe["region_code"] == "370100"
    assert safe["region_name"] == "济南市"
    assert safe["org_name"] == "省大数据局"
    assert safe["user_type"] == "0"
    assert safe["is_admin"] == 0
    # Idempotent: masking a masked dict produces the same mask (safe to re-apply)
    safe_again = apply_field_masks(safe, role="external")
    assert safe_again == safe
