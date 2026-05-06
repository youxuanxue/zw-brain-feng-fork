"""Streaming mysqldump parser.

Yields (table_name, row_dict) tuples. Designed for `--extended-insert` dumps where each
multi-row INSERT lives on a single (potentially very long) line. Memory footprint is one
INSERT statement at a time.

Handles:
    - CREATE TABLE blocks: extracts column order so VALUES tuples can be zipped into dicts
    - Quoted strings with mysqldump escape sequences (\\n \\t \\r \\0 \\\\ \\' \\" \\Z)
    - NULL keyword
    - Numeric, hex, and bare identifier scalars
    - Multi-row INSERTs: `INSERT INTO `t` VALUES (...),(...),...;`

Does NOT handle (rejected by design — these are not in the dumps we care about):
    - Stored procedures / triggers / events
    - LOAD DATA INFILE
    - Binary BLOB literals beyond mysqldump's hex form
"""
from __future__ import annotations

import io
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

CREATE_TABLE_OPEN_RE = re.compile(r"^CREATE TABLE `([^`]+)` \($")
COLUMN_DEF_RE = re.compile(r"^\s*`([^`]+)`\s")
INSERT_LINE_RE = re.compile(r"^INSERT INTO `([^`]+)` VALUES (.+);\s*$")

_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "Z": "\x1a",
    "b": "\b",
}


class MysqldumpParser:
    """Parse a mysqldump file once, yielding rows as dicts keyed by column name."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._columns_by_table: dict[str, list[str]] = {}

    @property
    def columns_by_table(self) -> dict[str, list[str]]:
        return dict(self._columns_by_table)

    def iter_rows(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield (table, row_dict) for every INSERT row in the dump."""
        in_create = None  # current table name when inside CREATE TABLE (...)
        with self.path.open("rb") as fh:
            buffered = io.BufferedReader(fh, buffer_size=1 << 20)
            for raw in buffered:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if in_create is not None:
                    if line.startswith(") ENGINE=") or line.startswith(")"):
                        in_create = None
                        continue
                    col_match = COLUMN_DEF_RE.match(line)
                    if col_match:
                        col_name = col_match.group(1)
                        self._columns_by_table.setdefault(in_create, []).append(col_name)
                    continue
                create_match = CREATE_TABLE_OPEN_RE.match(line)
                if create_match:
                    in_create = create_match.group(1)
                    self._columns_by_table.setdefault(in_create, [])
                    continue
                insert_match = INSERT_LINE_RE.match(line)
                if insert_match:
                    table = insert_match.group(1)
                    columns = self._columns_by_table.get(table)
                    if not columns:
                        # CREATE TABLE not seen yet (some dumps put inserts before defs).
                        # Skip until we know the columns.
                        continue
                    payload = insert_match.group(2)
                    for row_tuple in _iter_value_tuples(payload):
                        if len(row_tuple) != len(columns):
                            # Malformed or column-count drift; skip safely instead of mapping wrong.
                            continue
                        yield table, dict(zip(columns, row_tuple, strict=True))


def parse_dump_rows(path: str | Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """Convenience wrapper for one-shot iteration."""
    yield from MysqldumpParser(path).iter_rows()


def _iter_value_tuples(payload: str) -> Iterator[list[Any]]:
    """Iterate over `(...),(...),(...)` tuples in a VALUES clause."""
    n = len(payload)
    i = 0
    while i < n:
        # Skip whitespace and commas between tuples
        while i < n and payload[i] in (" ", "\t", ","):
            i += 1
        if i >= n:
            return
        if payload[i] != "(":
            # Garbage; bail
            return
        i += 1
        row, i = _parse_tuple(payload, i, n)
        yield row


def _parse_tuple(payload: str, i: int, n: int) -> tuple[list[Any], int]:
    row: list[Any] = []
    while i < n:
        # Skip leading whitespace
        while i < n and payload[i] in (" ", "\t"):
            i += 1
        if i >= n:
            break
        c = payload[i]
        if c == ")":
            return row, i + 1
        if c == "'":
            value, i = _parse_quoted_string(payload, i + 1, n)
            row.append(value)
        elif payload[i:i + 4] == "NULL" and (i + 4 == n or payload[i + 4] in (",", ")", " ", "\t")):
            row.append(None)
            i += 4
        else:
            # Bare token: number, hex (0x...), or unquoted identifier
            start = i
            while i < n and payload[i] not in (",", ")"):
                i += 1
            token = payload[start:i].strip()
            row.append(_parse_scalar(token))
        # Comma between values
        while i < n and payload[i] in (" ", "\t"):
            i += 1
        if i < n and payload[i] == ",":
            i += 1
    return row, i


def _parse_quoted_string(payload: str, i: int, n: int) -> tuple[str, int]:
    parts: list[str] = []
    while i < n:
        c = payload[i]
        if c == "\\" and i + 1 < n:
            nxt = payload[i + 1]
            parts.append(_ESCAPES.get(nxt, nxt))
            i += 2
        elif c == "'":
            return "".join(parts), i + 1
        else:
            parts.append(c)
            i += 1
    return "".join(parts), i


def _parse_scalar(token: str) -> Any:
    if not token:
        return ""
    if token.startswith("0x") or token.startswith("0X"):
        try:
            return bytes.fromhex(token[2:])
        except ValueError:
            return token
    # int / float — be permissive
    if token.lstrip("-").isdigit():
        try:
            return int(token)
        except ValueError:
            return token
    try:
        return float(token)
    except ValueError:
        return token
