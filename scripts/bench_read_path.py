#!/usr/bin/env python3
"""Read-path performance benchmark — data.search + topic.package.query.

Builds a *representative scaled* DB through the real ORM repositories (no mock
of business logic — only scale-up of the seed shape) so the N+1 collapse on
`topic.package.query{status:published}` and `data.search` is measurable, then
times each query and counts how many DB sessions (`SessionLocal()` checkouts)
each one opens.

Why a synthetic-scaled DB: the 116-package representative library is rebuilt
from real customer dumps (`scripts/customer_acceptance_up.sh`) which are not
present in every worktree. Correctness stays pinned to the real seed snapshot's
3 benchmark packages (see tests/integration/test_wave2_topic_package_*). This
script only *scales* package/catalog/asset counts to surface the per-N cost;
shapes and code paths exercised are the production read paths.

Usage:
    .venv/bin/python scripts/bench_read_path.py [--packages N] [--catalogs M]

Env: writes to a throwaway DB under .data/bench_read_path.db (removed first).
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DB = REPO_ROOT / ".data" / "bench_read_path.db"
TENANT = "sd-default"


def _reset_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        (BENCH_DB.parent / f"{BENCH_DB.name}{suffix}").unlink(missing_ok=True)
    BENCH_DB.parent.mkdir(parents=True, exist_ok=True)
    os.environ["ZW_BRAIN_DB_PATH"] = str(BENCH_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade
    reset_and_upgrade()


def _seed(packages: int, catalogs: int, legacy_tail: int = 60000) -> None:
    """Seed a representative-scale DB through the real repositories."""
    from zw_brain.domain.repositories import (
        CatalogRepository,
        DeliveryRepository,
        LegacyObjectMappingRepository,
        ResourceApiRepository,
        TopicPackageRepository,
    )

    cat_repo = CatalogRepository()
    asset_repo = ResourceApiRepository()
    tp_repo = TopicPackageRepository()
    legacy_repo = LegacyObjectMappingRepository()
    DeliveryRepository()

    # Catalog entries + items + assets. Each catalog gets 1 asset + 3 items.
    for ci in range(catalogs):
        code = f"basic-elem:bench-{ci:04d}"
        cat_repo.upsert_from_resource(
            {
                "id": code,
                # keyword "法人" lives in the title so search_entries' Python
                # substring filter (record.title) matches — surfaces the per-hit
                # topic_projection_cards N+1 the bench is meant to measure.
                "name": f"法人 基准目录 {ci}",
                "status": "active",
                "provider": f"org-{ci % 20}",
                "source_ref": f"bench:catalog:{ci}",
                "legacy_object_ref": code,
                "desc": "基准目录描述 法人 企业",
                "fields": ["f1", "f2"],
            },
            tenant_id=TENANT,
        )
        asset_repo.upsert_asset(
            {
                "resource_code": f"res-bench-{ci:04d}",
                "title": f"基准资源 {ci}",
                "resource_kind": "dataset",
                "lifecycle_status": "active",
                "owner_org_id": f"org-{ci % 20}",
                "catalog_code": code,
                "source_ref": f"bench:resource:{ci}",
                "legacy_object_ref": f"res-bench-{ci:04d}",
                "summary_json": {"domain": "bench"},
            },
            tenant_id=TENANT,
        )
        for fi in range(3):
            cat_repo.upsert_item(
                {
                    "item_code": f"{code}:field-{fi}",
                    "catalog_code": code,
                    "title": f"字段 {fi}",
                    "item_kind": "field",
                    "display_order": fi,
                    "summary_json": {},
                },
                tenant_id=TENANT,
            )

    # Legacy object mappings: one resource_asset mapping per asset (keyed by
    # resource_code) + a fat unrelated tail so the full-table prefetch the
    # scope-pushdown eliminates is measurable (production legacy_object_mapping
    # is ~68925 rows; default tail mirrors that scale).
    for ci in range(catalogs):
        legacy_repo.upsert_mapping(
            {
                "source_ref": f"bench:legacy:resource_asset:{ci}",
                "legacy_system": "DSP",
                "legacy_object_type": "dsp_resource",
                "legacy_object_ref": f"legacy-res-bench-{ci:04d}",
                "canonical_type": "resource_asset",
                "canonical_ref": f"res-bench-{ci:04d}",
            },
            tenant_id=TENANT,
        )
    for ti in range(legacy_tail):
        legacy_repo.upsert_mapping(
            {
                "source_ref": f"bench:legacy:tail:{ti}",
                "legacy_system": "DSP",
                "legacy_object_type": "service_invocation_metric",
                "legacy_object_ref": f"tail-{ti}",
                "canonical_type": "service_invocation_metric_projection",
                "canonical_ref": f"metric-{ti}",
            },
            tenant_id=TENANT,
        )

    # Topic packages: each references 2 catalog entries, published, with 1 approved visibility.
    for pi in range(packages):
        code = f"tp-bench-{pi:04d}"
        c0 = f"basic-elem:bench-{(pi * 2) % catalogs:04d}"
        c1 = f"basic-elem:bench-{(pi * 2 + 1) % catalogs:04d}"
        tp_repo.create_package(
            {
                "package_code": code,
                "title": f"基准专题包 {pi}",
                "scenario": "基准场景",
                "status": "draft",
                "display_snapshot_json": {"projection_kind": "topic_package"},
                "source_ref": f"bench:tp:{pi}",
            },
            tenant_id=TENANT,
        )
        tp_repo.configure_package(
            code,
            {
                "items": [
                    {"ref_type": "catalog_entry", "ref_id": c0, "title": "目录1", "display_order": 0},
                    {"ref_type": "catalog_entry", "ref_id": c1, "title": "目录2", "display_order": 1},
                ],
                "visibility": [
                    {"org_code": f"org-{pi % 20}", "role_code": "ROLE_ORGAN_OPERATER", "surface": "webui", "intent": "view", "policy_status": "approved"},
                ],
            },
            tenant_id=TENANT,
        )
        tp_repo.transition_package(code, "submitted", {"action_type": "submit"}, tenant_id=TENANT)
        tp_repo.transition_package(code, "published", {"action_type": "publish"}, tenant_id=TENANT)


class _LegacyRowCounter:
    """Count legacy_object_mapping rows list_mappings materializes (HIGH-1 / MEDIUM-1).

    The scope-pushdown win shows up here: a full-table prefetch loads ~68k
    rows; the scoped prefetch loads only the rows the page references.
    """

    def __enter__(self):
        import zw_brain.domain.repositories.legacy_mapping as lm

        self.rows = 0
        self._orig = lm.LegacyObjectMappingRepository.list_mappings
        counter = self

        def wrapped(repo_self, **kw):
            out = counter._orig(repo_self, **kw)
            counter.rows += len(out)
            return out

        lm.LegacyObjectMappingRepository.list_mappings = wrapped  # type: ignore[method-assign]
        self._lm = lm
        return self

    def __exit__(self, *exc):
        self._lm.LegacyObjectMappingRepository.list_mappings = self._orig  # type: ignore[method-assign]


class _SessionCounter:
    """Count create_session_factory() checkouts across every zw_brain module."""

    def __init__(self) -> None:
        self.count = 0

    def __enter__(self):
        import sys

        import zw_brain.shared.db as dbmod

        self._orig = dbmod.create_session_factory
        counter = self

        def wrapped():
            factory = counter._orig()

            def make():
                counter.count += 1
                return factory()

            return make

        self._patched = []
        for name, mod in list(sys.modules.items()):
            if name.startswith("zw_brain") and getattr(mod, "create_session_factory", None) is not None:
                mod.__dict__["create_session_factory"] = wrapped
                self._patched.append(mod)
        return self

    def __exit__(self, *exc):
        for mod in self._patched:
            mod.__dict__["create_session_factory"] = self._orig


def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss)


def _time(fn, *, repeat: int = 3):
    # warm once (engine/pragmas), then time.
    fn()
    best = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packages", type=int, default=87, help="topic packages (default 87 ~ published subset of 116)")
    ap.add_argument("--catalogs", type=int, default=120, help="catalog entries")
    ap.add_argument("--query", default="法人", help="data.search keyword")
    args = ap.parse_args()

    _reset_db()
    print(f"seeding: {args.packages} packages, {args.catalogs} catalogs ...", flush=True)
    _seed(args.packages, args.catalogs)

    brain = _new_brain()
    from zw_brain.command.handlers.j1 import data_search

    pkg_count = len(brain._state_store.database_store.topic_package_repo.list_packages(tenant_id=TENANT, status="published"))
    cat_count = brain._state_store.database_store.catalog_repo.count_entries(tenant_id=TENANT)
    print(f"DB ready: {pkg_count} published packages, {cat_count} catalog entries\n", flush=True)

    def run_tp_query():
        from zw_brain.command.deps import SkillContext
        from zw_brain.command.handlers.j2 import topic_package as tp
        deps = brain._get_handler_deps()
        ctx = SkillContext(
            skill_id="topic.package.query",
            role="ROLE_ORGAN_OPERATER",
            actor="bench-actor",
            confirmed=False,
            manifest={},
        )
        return tp._query_topic_packages(brain, deps, ctx, package_code=None, status="published")

    def run_data_search():
        return data_search.search_resources(brain, args.query, 1)

    def run_resource_api_query():
        # resource.api.query (no resource_code) → provider asset list enrich.
        # This is the HIGH-1 path: it previously prefetched the whole
        # legacy_object_mapping table on every render.
        from zw_brain.command.deps import SkillContext
        from zw_brain.command.handlers.j1 import resource_api
        deps = brain._get_handler_deps()
        ctx = SkillContext(
            skill_id="resource.api.query",
            role="ROLE_ORGAN_OPERATER",
            actor="bench-actor",
            confirmed=False,
            manifest={},
        )
        return resource_api._query_resource_assets(brain, deps, ctx, resource_code=None)

    # session counts
    with _SessionCounter() as c:
        out = run_tp_query()
    tp_sessions = c.count
    tp_items = len(out["items"])

    with _SessionCounter() as c:
        out2 = run_data_search()
    ds_sessions = c.count
    ds_total = out2["total"]

    # resource.api.query: count both sessions AND legacy_object_mapping rows
    # loaded (HIGH-1 scope pushdown headline metric).
    with _LegacyRowCounter() as lc:
        ra_out = run_resource_api_query()
    ra_legacy_rows = lc.rows
    ra_items = len(ra_out.get("items", []))

    tp_ms = _time(run_tp_query) * 1000
    ds_ms = _time(run_data_search) * 1000
    ra_ms = _time(run_resource_api_query) * 1000

    full_table = len(brain._state_store.database_store.legacy_mapping_repo.list_mappings(tenant_id=TENANT))

    print("=" * 78)
    print(f"{'query':<34}{'latency(ms)':>14}{'sessions':>12}{'legacy rows':>16}")
    print("-" * 78)
    tp_label = "topic.package.query{published}"
    ds_label = f'data.search("{args.query}")'
    ra_label = "resource.api.query{list}"
    print(f"{tp_label:<34}{tp_ms:>14.1f}{tp_sessions:>12}{'—':>16}  ({tp_items} items)")
    print(f"{ds_label:<34}{ds_ms:>14.1f}{ds_sessions:>12}{'—':>16}  ({ds_total} hits)")
    print(f"{ra_label:<34}{ra_ms:>14.1f}{'—':>12}{ra_legacy_rows:>16}  ({ra_items} assets)")
    print("=" * 78)
    print(
        f"legacy_object_mapping full table = {full_table} rows; "
        f"resource.api.query scoped prefetch loaded {ra_legacy_rows} "
        f"(HIGH-1: was full-table on every render)"
    )


if __name__ == "__main__":
    main()
