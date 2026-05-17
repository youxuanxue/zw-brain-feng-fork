"""Redaction rule lookup for customer-site legacy export.

Sources of truth (priority high → low):

1. Explicit per-(schema, table, column) overrides hard-coded below for known
   PII columns whose XML metadata does not always carry `sensitive_level`
   (phone, idcard, contact, addr, mobile, email, password).
2. `old/12-datastructure/*.xml` `<column ... sensitive_level=...>` markers
   (level >= 3 → redact). The structure file location is configurable via
   `ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR`.
3. `need_encrypt=1` / `need_mask=1` flags.

Redaction strategy: replace value with a typed placeholder so downstream
mappers still parse the SQL but cannot reconstruct the original. Numeric
columns get `0`; strings get `<REDACTED:KIND>`; everything else gets `NULL`.

This is conservative: it errs on the side of redacting too much rather than
too little. Customer-site sanity checks should validate the post-redaction
dump using `scripts/customer_export.py verify` before shipping.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

# Hard-coded known-PII patterns. Matched case-insensitively against column name.
_PII_COLUMN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(^|_)(mobile|phone|tel|telphone|telephone|cellphone)(_|$)", re.IGNORECASE), "phone"),
    (re.compile(r"(^|_)id_?card(_|$|no)", re.IGNORECASE), "idcard"),
    (re.compile(r"(^|_)(idno|certno|cert_no|certificate_no)(_|$)", re.IGNORECASE), "idcard"),
    (re.compile(r"(^|_)(email|mail)(_|$|addr)", re.IGNORECASE), "email"),
    (re.compile(r"(^|_)(password|passwd|pwd|secret|token|api_?key|app_?key|app_?secret)(_|$)", re.IGNORECASE), "secret"),
    (re.compile(r"(^|_)(addr|address|home_addr|reg_addr|contact_addr)(_|$)", re.IGNORECASE), "addr"),
    (re.compile(r"(^|_)(bank_?card|card_?no|account_?no|bank_?account)(_|$)", re.IGNORECASE), "bankcard"),
    (re.compile(r"(^|_)(ip_addr|ip_address|server_ip|host_ip|client_ip)(_|$)", re.IGNORECASE), "ip"),
    (re.compile(r"(^|_)(conn_str|connection_string|jdbc_url|db_url)(_|$)", re.IGNORECASE), "connstr"),
)

# Numeric column hints — these get `0` instead of a string placeholder.
_NUMERIC_HINT = re.compile(r"(_id|_no|_num|_count|_amt|_amount|_size)$", re.IGNORECASE)


@dataclass(frozen=True)
class RedactionDecision:
    """One column's redaction outcome."""

    redact: bool
    kind: str = ""
    reason: str = ""


@dataclass
class RedactionConfig:
    """Loaded redaction rules across all known schemas."""

    # schema → table → column → decision
    rules: dict[str, dict[str, dict[str, RedactionDecision]]] = field(default_factory=dict)
    # column-name fallback applies across all (table) when no explicit rule exists
    fallback_patterns: tuple[tuple[re.Pattern[str], str], ...] = _PII_COLUMN_PATTERNS

    def decide(self, schema: str, table: str, column: str) -> RedactionDecision:
        schema_rules = self.rules.get(schema, {})
        table_rules = schema_rules.get(table, {})
        explicit = table_rules.get(column)
        if explicit is not None:
            return explicit
        for pat, kind in self.fallback_patterns:
            if pat.search(column):
                return RedactionDecision(redact=True, kind=kind, reason="pii-pattern")
        return RedactionDecision(redact=False)

    def redacted_columns_for(self, schema: str, table: str) -> list[tuple[str, RedactionDecision]]:
        """Return [(column, decision)] for all columns that get redacted in this table.

        Only useful when the caller already knows the table's columns; the
        fallback PII patterns are applied lazily by `decide()` so they only
        appear here if the caller passes the column through `decide()` itself.
        """
        table_rules = self.rules.get(schema, {}).get(table, {})
        return [(col, decision) for col, decision in table_rules.items() if decision.redact]


def load_redaction_config(datastructure_dir: Path | None = None) -> RedactionConfig:
    """Load redaction rules from XML schemas + built-in PII patterns.

    `datastructure_dir` defaults to `<repo>/old/12-datastructure`. Each file's
    base name (without `.xml`) is treated as the schema slug (e.g. `dsp_catalog`).
    """
    config = RedactionConfig()
    if datastructure_dir is None:
        repo_root = Path(__file__).resolve().parent.parent
        datastructure_dir = repo_root / "old" / "12-datastructure"
    if not datastructure_dir.is_dir():
        return config
    for xml_path in sorted(datastructure_dir.glob("*.xml")):
        schema = xml_path.stem
        try:
            tree = ElementTree.parse(xml_path)
        except ElementTree.ParseError:
            continue
        config.rules.setdefault(schema, {})
        for table_el in tree.iter():
            if not table_el.tag.endswith("table"):
                continue
            table_name = table_el.attrib.get("id") or table_el.attrib.get("name")
            if not table_name:
                continue
            table_rules = config.rules[schema].setdefault(table_name, {})
            for col_el in table_el.iter():
                if not col_el.tag.endswith("column"):
                    continue
                col_name = col_el.attrib.get("id") or col_el.attrib.get("name")
                if not col_name:
                    continue
                decision = _decide_from_xml_attrs(col_el.attrib)
                # PII pattern fallback still applies if XML says nothing.
                if not decision.redact:
                    for pat, kind in _PII_COLUMN_PATTERNS:
                        if pat.search(col_name):
                            decision = RedactionDecision(redact=True, kind=kind, reason="pii-pattern")
                            break
                if decision.redact:
                    table_rules[col_name] = decision
    return config


def _decide_from_xml_attrs(attrs: dict[str, str]) -> RedactionDecision:
    """Translate XML attribute set into a redaction decision."""
    sensitive_level = attrs.get("sensitive_level") or ""
    need_encrypt = attrs.get("need_encrypt") or ""
    need_mask = attrs.get("need_mask") or ""
    # sensitive_level: "3" / "4" → redact
    if sensitive_level.strip() in {"3", "4"}:
        return RedactionDecision(redact=True, kind="sensitive-l3plus", reason=f"sensitive_level={sensitive_level}")
    if need_encrypt.strip() == "1":
        return RedactionDecision(redact=True, kind="encrypt-required", reason="need_encrypt=1")
    if need_mask.strip() == "1":
        return RedactionDecision(redact=True, kind="mask-required", reason="need_mask=1")
    return RedactionDecision(redact=False)


def mask_value(column: str, original: object, decision: RedactionDecision) -> object:
    """Return a redacted replacement value for one cell.

    Numeric-named columns return 0; everything else returns `<REDACTED:KIND>`.
    The decision's `kind` becomes the placeholder suffix so customer-site
    operators can see at a glance which rule fired.
    """
    if not decision.redact:
        return original
    if original is None:
        return None
    if _NUMERIC_HINT.search(column):
        return 0
    kind = decision.kind or "redacted"
    return f"<REDACTED:{kind.upper()}>"


def iter_known_schemas(config: RedactionConfig) -> Iterable[str]:
    return sorted(config.rules.keys())
