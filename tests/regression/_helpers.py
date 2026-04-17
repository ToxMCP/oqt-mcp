import json
from pathlib import Path

_SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"


_VOLATILE_KEYS = {
    "workflowId",
    "generatedAt",
    "generatedBy",
    "entityId",
    "requestedAt",
    "executionTimestamp",
    "inputHash",
    "snapshotHash",
    "durationMs",
    "duration_ms",
    "last_attempt_ms",
    "total_duration_ms",
    "attempts",
    "timeoutProfile",
    "statusCode",
    "checksumSha256",
    "sizeBytes",
}


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {
            k: _strip_volatile(v)
            for k, v in obj.items()
            if k not in _VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_volatile(item) for item in obj]
    return obj


def normalize_for_snapshot(data: dict) -> dict:
    """Return a deterministic copy of the handoff data with volatile fields removed."""
    return _strip_volatile(data)


def load_snapshot(name: str) -> dict | None:
    path = _SNAPSHOT_DIR / f"{name}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_snapshot(name: str, data: dict) -> None:
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _SNAPSHOT_DIR / f"{name}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
