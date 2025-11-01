# Observability & Audit Logging

## Correlation IDs
- Every request receives a UUID-based correlation id.
- The middleware attaches the id to `request.state.correlation_id`, emits it in audit events, and returns it in the `X-Request-ID` response header.
- Downstream services should include this value in logs when interacting with the MCP server.

## Audit Events
- Audit payloads are emitted via `src.utils.audit.emit`, which supports pluggable sinks.
- Default behaviour logs to the standard logger when no sink is registered.
- Sinks can be registered with `register_sink` (synchronous callables). A helper `clear_sinks` is available for tests.
- Current events:
  - `http_request`: method, path, status, latency, user (if authenticated).
  - `tool_execution`: emitted on success, forbidden access, and execution errors.

## Extending Audit Sinks
- Implement a callable `def sink(event: dict) -> None`.
- Register the sink during startup (e.g., in `src/api/server.py`) to forward events to SIEM, message bus, etc.
- Sink errors are caught and logged to avoid disrupting the main request flow.

## Structured Logging
- `src/utils/logging.setup_logging` configures JSON logs using `python-json-logger` with fields `timestamp`, `level`, `name`, and message.
- Audit middleware and RBAC logic log contextual information (role, tool, correlation id) via `extra`.

## Metrics Hooks
- RBAC decisions emit metrics via `_emit_metric` (currently a logging stub). Integrate with Prometheus/OpenTelemetry as needed.

## Testing
- See `tests/api/test_audit_middleware.py` for a pattern that registers a temporary sink and asserts events/correlation ids.
