"""Shared PostgreSQL admin helpers for tests that create/drop databases."""

from __future__ import annotations

import os
import time

import psycopg
from psycopg import sql


def maintenance_connect(server_url) -> psycopg.Connection:
    """Autocommit connection to the maintenance DB for CREATE/DROP DATABASE."""
    maint_db = os.environ.get("ZW_BRAIN_TEST_PG_MAINTENANCE_DB", "postgres")
    return psycopg.connect(
        host=server_url.host,
        port=server_url.port,
        user=server_url.username,
        password=server_url.password,
        dbname=maint_db,
        autocommit=True,
    )


def drop_database(maint: psycopg.Connection, name: str) -> None:
    """Drop a database, retrying transient low-privilege FORCE failures.

    PG 16 ``DROP DATABASE ... WITH (FORCE)`` can still raise when a low-privilege
    test role briefly cannot terminate a lingering backend. Retrying lets normal
    connection cleanup settle while still surfacing real leaks.
    """
    delays = (0.05, 0.1, 0.2, 0.5, 1.0)
    for attempt, delay in enumerate((*delays, 0.0)):
        try:
            maint.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            return
        except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectInUse):
            if attempt == len(delays):
                raise
            time.sleep(delay)
