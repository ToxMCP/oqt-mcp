import logging
import re
import sys

from pythonjsonlogger import jsonlogger

from src.config.settings import settings
from src.utils.privacy import scrub_value

# Patterns that indicate sensitive data in free-text log messages
_SENSITIVE_PATTERNS = [
    (re.compile(r"SMILES:\s*([A-Za-z0-9=@+\-\[\]\\\(\)/#.]+)", re.IGNORECASE), "SMILES: [HASHED]"),
    (re.compile(r"CAS\s*:?\s*(\d{1,7}-\d{2}-\d)", re.IGNORECASE), "CAS: [HASHED]"),
    (re.compile(r"chemical_name[=:]\s*([^,\s]+)", re.IGNORECASE), "chemical_name=[HASHED]"),
    # Scrub SMILES/CAS from URLs in httpx logs
    (re.compile(r"([?&]smiles=)[^\s\"']+", re.IGNORECASE), r"\1[HASHED]"),
    (re.compile(r"([?&]cas=)[^\s\"']+", re.IGNORECASE), r"\1[HASHED]"),
    (re.compile(r"([?&]query=)[^\s\"']+", re.IGNORECASE), r"\1[HASHED]"),
]


class PrivacyLogFilter(logging.Filter):
    """Redact sensitive identifiers from log records before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Merge format string with args so we can scrub the final message
        try:
            merged = record.getMessage()
        except (TypeError, ValueError):
            merged = str(record.msg)

        scrubbed = merged
        for pattern, replacement in _SENSITIVE_PATTERNS:
            scrubbed = pattern.sub(replacement, scrubbed)

        # Also apply whole-value scrubbing for direct SMILES/CAS in the message
        scrubbed = scrub_value("message", scrubbed)

        # Replace record.msg with scrubbed merged message and clear args
        record.msg = scrubbed
        record.args = None

        # Scrub any extra fields that might contain identifiers
        for key in ("smiles", "identifier", "query", "api_key", "llm_api_key", "path"):
            if hasattr(record, key):
                value = getattr(record, key)
                if isinstance(value, str):
                    setattr(record, key, scrub_value(key, value))

        return True


def setup_logging():
    """Configures structured JSON logging (Section 3.3)."""
    logger = logging.getLogger()

    # Set the log level from configuration
    try:
        logger.setLevel(settings.app.LOG_LEVEL)
    except ValueError:
        logger.setLevel(logging.INFO)

    # Remove default handlers
    if logger.handlers:
        logger.handlers = []

    # Create a stream handler for stdout
    handler = logging.StreamHandler(sys.stdout)

    # Use JSON formatter for structured logging
    # This is crucial for observability and audit trails (Section 2.3)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    handler.addFilter(PrivacyLogFilter())
    logger.addHandler(handler)


# Configure logging globally upon import
setup_logging()
log = logging.getLogger(__name__)
