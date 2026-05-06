"""Regression tests for the mysqldump streaming parser."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from zw_brain.adapters.legacy import LegacyImportRunner, MysqldumpParser
from zw_brain.adapters.legacy.parser import _iter_value_tuples


SAMPLE_DUMP = """\
-- MySQL dump 10.13
--
-- Host: localhost    Database: test_db
-- ------------------------------------------------------

--
-- Table structure for table `data_example`
--

DROP TABLE IF EXISTS `data_example`;
CREATE TABLE `data_example` (
  `id` varchar(64) NOT NULL,
  `example_name` varchar(255) DEFAULT NULL,
  `org_code` varchar(64) DEFAULT NULL,
  `visit_count` int(11) DEFAULT '0',
  `is_active` tinyint(1) DEFAULT '0',
  `payload_text` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--
-- Dumping data for table `data_example`
--

INSERT INTO `data_example` VALUES ('id-1','公司变更登记','11370000MB284651XL',14,1,'多行\\n描述\\t带 tab'),('id-2','婚姻登记\\'全省通办\\'','11370000004504927A',0,0,NULL),('id-3','空摘要','370000000000',-3,1,'');

--
-- Table structure for table `data_example_contact`
--

DROP TABLE IF EXISTS `data_example_contact`;
CREATE TABLE `data_example_contact` (
  `id` varchar(64) NOT NULL,
  `contact_name` varchar(64) DEFAULT NULL,
  `phone` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;

INSERT INTO `data_example_contact` VALUES ('c-1','张三','13800001111');
"""


def _write_sample_dump(dirpath: Path, content: str = SAMPLE_DUMP) -> Path:
    path = dirpath / "dump-test_db-202604000000.sql"
    path.write_text(content, encoding="utf-8")
    return path


def test_parser_extracts_columns_and_values_with_escapes() -> None:
    with TemporaryDirectory() as tmp:
        dump = _write_sample_dump(Path(tmp))
        rows = list(MysqldumpParser(dump).iter_rows())

    assert len(rows) == 4
    by_table: dict[str, list[dict]] = {}
    for table, row in rows:
        by_table.setdefault(table, []).append(row)

    assert set(by_table.keys()) == {"data_example", "data_example_contact"}

    examples = by_table["data_example"]
    assert examples[0]["id"] == "id-1"
    assert examples[0]["example_name"] == "公司变更登记"
    assert examples[0]["visit_count"] == 14
    assert examples[0]["is_active"] == 1
    assert examples[0]["payload_text"] == "多行\n描述\t带 tab"

    # Single-quote escape inside string + NULL handling
    assert examples[1]["example_name"] == "婚姻登记'全省通办'"
    assert examples[1]["payload_text"] is None

    # Negative integer + empty string
    assert examples[2]["visit_count"] == -3
    assert examples[2]["payload_text"] == ""

    contact = by_table["data_example_contact"][0]
    assert contact["contact_name"] == "张三"
    assert contact["phone"] == "13800001111"


def test_runner_parse_stats_and_jsonl_cache_roundtrip() -> None:
    with TemporaryDirectory() as tmp:
        dumps_dir = Path(tmp) / "dumps"
        dumps_dir.mkdir()
        cache_dir = Path(tmp) / ".legacy_cache"
        _write_sample_dump(dumps_dir)

        import os
        os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(dumps_dir)

        runner = LegacyImportRunner(cache_dir=cache_dir)
        stats = runner.parse_schema("test_db")
        assert stats.total_rows == 4
        assert stats.table_row_counts == {"data_example": 3, "data_example_contact": 1}
        assert stats.skipped_tables == []

        out = runner.write_jsonl_cache("test_db")
        assert (out / "data_example.jsonl").exists()
        with (out / "data_example.jsonl").open("r", encoding="utf-8") as fh:
            cached = [json.loads(line) for line in fh]
        assert [r["id"] for r in cached] == ["id-1", "id-2", "id-3"]
        # NULL preserved through JSON roundtrip
        assert cached[1]["payload_text"] is None
        # Truncation kicks in
        capped = runner.write_jsonl_cache("test_db", max_rows_per_table=1)
        with (capped / "data_example.jsonl").open("r", encoding="utf-8") as fh:
            assert sum(1 for _ in fh) == 1


def test_iter_value_tuples_handles_multi_row_inserts() -> None:
    payload = "(1,'a',NULL),(2,'b\\\\c',3.14),(3,0xFF,'')"
    tuples = list(_iter_value_tuples(payload))
    assert tuples == [
        [1, "a", None],
        [2, "b\\c", 3.14],
        [3, b"\xff", ""],
    ]
