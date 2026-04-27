from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaInfo:
    name: str
    purpose: str


SCHEMAS = (
    SchemaInfo(name="brain_core", purpose="主旅程聚合与状态机"),
    SchemaInfo(name="brain_audit", purpose="审计事件与回执"),
    SchemaInfo(name="brain_registry", purpose="能力注册与暴露治理"),
)


def describe_schemas() -> list[dict[str, str]]:
    return [{"name": item.name, "purpose": item.purpose} for item in SCHEMAS]
