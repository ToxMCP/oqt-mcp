import logging
from typing import Callable, Dict, List

log = logging.getLogger(__name__)

AuditEvent = Dict[str, object]
AuditSink = Callable[[AuditEvent], None]

_sinks: List[AuditSink] = []


def register_sink(sink: AuditSink) -> None:
    if sink not in _sinks:
        _sinks.append(sink)


def clear_sinks() -> None:
    _sinks.clear()


def emit(event: AuditEvent) -> None:
    if not _sinks:
        log.info("AUDIT_EVENT", extra={"event": event})
        return

    for sink in _sinks:
        try:
            sink(event)
        except Exception as exc:  # pragma: no cover - defensive
            log.error("Audit sink %s failed: %s", sink, exc)
