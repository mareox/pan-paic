"""Structured JSON logging configuration with redaction filter."""

import logging
import re
from datetime import UTC, datetime

# Pattern that matches sensitive values in log messages/args
SENSITIVE_PATTERN = re.compile(
    r"(api[_-]?key\s*=\s*\S+|authorization\s*[:\s]\s*\S+|bearer\s+\S+|header-api-key\s*[:\s]\s*\S+)",
    re.IGNORECASE,
)

_REDACTED = "***REDACTED***"


def _redact(value: str) -> str:
    """Replace sensitive patterns in a string with REDACTED."""
    return SENSITIVE_PATTERN.sub(_REDACTED, value)


class RedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive values before emission."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (_redact(v) if isinstance(v, str) else v) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


class _JsonFormatter(logging.Formatter):
    """Single-line JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = f"{record.msg!s} args={record.args!r}"
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

        parts: list[str] = [
            f'"ts":"{ts}"',
            f'"level":"{record.levelname}"',
            f'"logger":"{record.name}"',
            f'"msg":{_json_str(message)}',
        ]

        # Append any extra fields set on the record
        skip = {
            "name", "msg", "args", "created", "filename", "funcName", "levelname",
            "levelno", "lineno", "module", "msecs", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread", "threadName",
            "exc_info", "exc_text", "message",
        }
        for key, val in record.__dict__.items():
            if key not in skip:
                parts.append(f'"{key}":{_json_str(str(val))}')

        if record.exc_info:
            parts.append(f'"exc":{_json_str(self.formatException(record.exc_info))}')

        return "{" + ",".join(parts) + "}"


def _json_str(value: str) -> str:
    """Minimally escape a string for JSON embedding."""
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    )
    return f'"{escaped}"'


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with single-line JSON output and redaction."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
