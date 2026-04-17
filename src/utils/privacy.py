"""Privacy scrubbing for audit logs and telemetry."""

import hashlib
import re
from typing import Any


# SMILES heuristic: typical SMILES characters
_SMILES_CHARS = set("CNO[]()=@+-#$.1234567890BSIPFclbr/\\")
# CAS number pattern
_CAS_PATTERN = re.compile(r"^\d{1,7}\-\d{2}\-\d$")

_SENSITIVE_KEYS = {
    "smiles",
    "inchi",
    "inchikey",
    "cas",
    "cas_number",
    "chemical_name",
    "preferred_name",
    "iupac_name",
    "structure",
    "molecule",
    "compound",
    "substance",
    "formula",
    "identifier",
    "query",
    "llm_api_key",
    "api_key",
}


def _looks_like_smiles(value: str) -> bool:
    if len(value) < 3:
        return False
    value_chars = set(value.upper())
    # Must contain at least one structural SMILES character to reduce false positives
    structural_chars = set("()[]=@#+-1234567890")
    if not (value_chars & structural_chars):
        return False
    # If most chars are SMILES-specific, treat as SMILES
    return len(value_chars - _SMILES_CHARS) <= 2


def _hash_value(value: str, salt: str = "oqt_mcp_audit") -> str:
    digest = hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]
    return f"[HASH:{digest}]"


def scrub_value(key: str, value: Any) -> Any:
    """
    Scrub a single value based on its key name and content heuristics.
    Returns a privacy-safe replacement or the original value.
    """
    if value is None:
        return None

    key_lower = str(key).lower()

    # Always scrub known sensitive keys
    if key_lower in _SENSITIVE_KEYS:
        return _hash_value(str(value))

    # Heuristic: if the value looks like a SMILES string
    if isinstance(value, str):
        stripped = value.strip()
        if _looks_like_smiles(stripped):
            return _hash_value(stripped)
        if _CAS_PATTERN.match(stripped):
            return _hash_value(stripped)

    return value


def scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub a dictionary of params before logging."""
    if not isinstance(data, dict):
        return {}
    scrubbed: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            scrubbed[key] = scrub_dict(value)
        elif isinstance(value, list):
            scrubbed[key] = [
                scrub_dict(item) if isinstance(item, dict) else scrub_value(key, item)
                for item in value
            ]
        else:
            scrubbed[key] = scrub_value(key, value)
    return scrubbed
