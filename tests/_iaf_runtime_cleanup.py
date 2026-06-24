"""IAF test runtime wrapper that disposes DB connections before fixture teardown."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from tests._iaf_rest_http import bootstrap_iaf_runtime
from zw_brain.shared import db as db_module


@contextmanager
def bootstrap_iaf_runtime_clean(tmp: str) -> Iterator[None]:
    db_module.reset_engine_cache()
    with bootstrap_iaf_runtime(tmp):
        try:
            yield
        finally:
            db_module.reset_engine_cache()
