from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from zw_brain.shared.logkit.formatter import ContextFilter, HumanFormatter, JsonLineFormatter

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_configured: str | None = None


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def setup_logging(service: str, *, force: bool = False) -> None:
    """Configure the ``zw_brain`` logger tree once per process (entry main() calls this).

    Only the ``zw_brain`` namespace logger is touched — never the root logger — so
    pytest caplog and third-party loggers keep their default behavior. The console
    handler always writes stderr (MCP stdout is the JSON-RPC channel); the optional
    rotating file sink (``ZW_BRAIN_LOG_DIR``) always emits JSON lines for grep/jq.
    Troubleshooting logging must never block startup: file-sink failures degrade to
    console-only. This is deliberately separate from the audit bus (D4) — log lines
    are best-effort observability, audit events are the durable compliance record.
    """
    global _configured
    if _configured is not None and not force:
        return

    level_name = (os.environ.get("ZW_BRAIN_LOG_LEVEL") or "INFO").strip().upper()
    if level_name not in _LOG_LEVELS:
        level_name = "INFO"
    console_format = (os.environ.get("ZW_BRAIN_LOG_FORMAT") or "text").strip().lower()

    logger = logging.getLogger("zw_brain")
    logger.setLevel(level_name)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    context_filter = ContextFilter()

    console = logging.StreamHandler(sys.stderr)
    console.addFilter(context_filter)
    console.setFormatter(
        JsonLineFormatter(service) if console_format == "json" else HumanFormatter()
    )
    logger.addHandler(console)

    log_dir = (os.environ.get("ZW_BRAIN_LOG_DIR") or "").strip()
    if log_dir:
        try:
            directory = Path(log_dir)
            directory.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                directory / f"{service}.log",
                maxBytes=_env_int("ZW_BRAIN_LOG_FILE_MAX_BYTES", 10 * 1024 * 1024),
                backupCount=_env_int("ZW_BRAIN_LOG_FILE_BACKUP_COUNT", 5),
                encoding="utf-8",
            )
            file_handler.addFilter(context_filter)
            file_handler.setFormatter(JsonLineFormatter(service))
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("log file sink unavailable (%s); console only", exc)

    _configured = service
