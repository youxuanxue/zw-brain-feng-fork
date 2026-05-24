"""Objection 5-dimension state machines (F1 catalog → F2 content/use/resource/authz).

# 命名取舍 (F2 work note)
─────────────────────
**采用 A：5 维度统一业务命名 catalog / content / use / resource / authz。**

理由：
1. plan.yaml F2 deliverable 与 AC1 措辞均使用 5 维度业务命名；
2. .testing/.../j1-objection-{authz,content,resource,use,catalog}.feature 文件命名同；
3. mapper 内部 `evidence_type` 是数据库子表名衍生（quality/usage/authorization），属
   存储层契约，业务命名应解耦。

`EVIDENCE_TO_DIMENSION_ALIAS` 把 mapper 写入的 5 个 evidence_type 一对一映射到 5
个业务维度名；handler、test、state 表统一使用业务维度命名。

# 真实数据派生 (sd-default `dump-dsp_handling` 27 条异议)
─────────────────────
| 维度       | case 数 | 真实出现 status                                                  |
| --------- | ------ | ---------------------------------------------------------------- |
| catalog   | 15     | draft, submitted, platform_investigating, provider_investigating, resolved, rejected (6) |
| authz     | 11*    | draft, platform_investigating, provider_investigating, resolved (4) |
| use       | 1      | platform_investigating (1)                                       |
| content   | 0      | —                                                                |
| resource  | 0      | —                                                                |

*authz 11 = 7 (kind=authorization) + 4 (kind=resource_quality 但 authz 子表也挂)。
evidence_type 优先于 objection_kind，符合 "证据驱动" 设计；交叉案例由 evidence-first 归类。

# Transition 表设计
─────────────────────
4 个新维度真实数据呈现的 status 集合**全部是 catalog 6 状态的子集**（authz=4 子集，
use=1 子集，content/resource=∅）。feature 规范 4 维度转换路径形态与 catalog 一致
（draft → submitted → 平台/部门核查 → resolved/rejected → closed）。因此 F2 采用**共享
同一张 transition 形状**的方式实现 5 维度，并通过独立常量名暴露分化点 —— 待 F3
evaluate/process 辅助流程或后续业务方明确分化需求时，从此处 split 各维度。

`closed` 终态由 objection.case.close 通用 handler 走，5 维度均支持。
"""

from __future__ import annotations

from collections.abc import Iterable

# ──────────────────────────────────────────────────────────────────────
# Dimension names (5 业务维度 + 1 generic 兜底)
# ──────────────────────────────────────────────────────────────────────

CATALOG_DIMENSION = "catalog"
CONTENT_DIMENSION = "content"
USE_DIMENSION = "use"
RESOURCE_DIMENSION = "resource"
AUTHZ_DIMENSION = "authz"
GENERIC_DIMENSION = "generic"

ALL_DIMENSIONS: tuple[str, ...] = (
    CATALOG_DIMENSION,
    CONTENT_DIMENSION,
    USE_DIMENSION,
    RESOURCE_DIMENSION,
    AUTHZ_DIMENSION,
)

# ──────────────────────────────────────────────────────────────────────
# Real-data observed status sets (用于 reachability 测试断言基准)
# ──────────────────────────────────────────────────────────────────────

REAL_STATES_BY_DIMENSION: dict[str, frozenset[str]] = {
    CATALOG_DIMENSION: frozenset(
        {
            "draft",
            "submitted",
            "platform_investigating",
            "provider_investigating",
            "resolved",
            "rejected",
        }
    ),
    AUTHZ_DIMENSION: frozenset(
        {"draft", "platform_investigating", "provider_investigating", "resolved"}
    ),
    USE_DIMENSION: frozenset({"platform_investigating"}),
    CONTENT_DIMENSION: frozenset(),
    RESOURCE_DIMENSION: frozenset(),
}

# ──────────────────────────────────────────────────────────────────────
# Transition table — 共享同一形状，5 维度别名分化点
# ──────────────────────────────────────────────────────────────────────

_SHARED_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"submitted"}),
    "submitted": frozenset({"platform_investigating", "rejected"}),
    "platform_investigating": frozenset(
        {"provider_investigating", "resolved", "rejected"}
    ),
    "provider_investigating": frozenset(
        {"platform_investigating", "resolved", "rejected"}
    ),
    "resolved": frozenset({"closed", "provider_investigating"}),
    "rejected": frozenset(),
    "closed": frozenset(),
}

# Public aliases — 每维度独立常量名，方便未来分化（split 后只改本表）
CATALOG_ALLOWED_TRANSITIONS = _SHARED_ALLOWED_TRANSITIONS
CONTENT_ALLOWED_TRANSITIONS = _SHARED_ALLOWED_TRANSITIONS
USE_ALLOWED_TRANSITIONS = _SHARED_ALLOWED_TRANSITIONS
RESOURCE_ALLOWED_TRANSITIONS = _SHARED_ALLOWED_TRANSITIONS
AUTHZ_ALLOWED_TRANSITIONS = _SHARED_ALLOWED_TRANSITIONS

ALLOWED_TRANSITIONS_BY_DIMENSION: dict[str, dict[str, frozenset[str]]] = {
    CATALOG_DIMENSION: CATALOG_ALLOWED_TRANSITIONS,
    CONTENT_DIMENSION: CONTENT_ALLOWED_TRANSITIONS,
    USE_DIMENSION: USE_ALLOWED_TRANSITIONS,
    RESOURCE_DIMENSION: RESOURCE_ALLOWED_TRANSITIONS,
    AUTHZ_DIMENSION: AUTHZ_ALLOWED_TRANSITIONS,
}

# Back-compat：F1 已有调用方继续按 frozenset 读
CATALOG_REACHABLE_STATES: frozenset[str] = REAL_STATES_BY_DIMENSION[CATALOG_DIMENSION]

# ──────────────────────────────────────────────────────────────────────
# Dimension inference — evidence_type alias → 业务维度名
# ──────────────────────────────────────────────────────────────────────

EVIDENCE_TO_DIMENSION_ALIAS: dict[str, str] = {
    "catalog": CATALOG_DIMENSION,
    "quality": CONTENT_DIMENSION,
    "usage": USE_DIMENSION,
    "resource": RESOURCE_DIMENSION,
    "authorization": AUTHZ_DIMENSION,
}

KIND_TO_DIMENSION: dict[str, str] = {
    "catalog_quality": CATALOG_DIMENSION,
    "resource_quality": RESOURCE_DIMENSION,
    "authorization": AUTHZ_DIMENSION,
    "usage": USE_DIMENSION,
}

TARGET_TO_DIMENSION: dict[str, str] = {
    "catalog": CATALOG_DIMENSION,
    "resource": RESOURCE_DIMENSION,
    "authorization": AUTHZ_DIMENSION,
    # "delivery" → 语义模糊（既可 use 也可 content），不在此处归类，回落 GENERIC
}


def dimension_of(
    case: object,
    evidences: Iterable[object] = (),
) -> str:
    """Infer dimension by (a) evidence_type, (b) objection_kind, (c) target_type.

    evidence-first：evidence_type 是 mapper 落库的真实业务证据标签，比 kind/target
    更精确。多 evidence 时取第一个能映射到业务维度的；catalog 维度因业务量大保持
    F1 优先短路语义（任何 evidence 含 catalog 即归 catalog）。
    """
    catalog_seen = False
    first_known: str | None = None
    for ev in evidences:
        et = getattr(ev, "evidence_type", None)
        if et not in EVIDENCE_TO_DIMENSION_ALIAS:
            continue
        dim = EVIDENCE_TO_DIMENSION_ALIAS[et]
        if dim == CATALOG_DIMENSION:
            catalog_seen = True
            break
        if first_known is None:
            first_known = dim
    if catalog_seen:
        return CATALOG_DIMENSION
    if first_known is not None:
        return first_known
    kind = getattr(case, "objection_kind", None)
    if kind in KIND_TO_DIMENSION:
        return KIND_TO_DIMENSION[kind]
    target = getattr(case, "target_type", None)
    if target in TARGET_TO_DIMENSION:
        return TARGET_TO_DIMENSION[target]
    return GENERIC_DIMENSION
