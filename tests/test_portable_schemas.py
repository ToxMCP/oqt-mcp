import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


SCHEMA_EXAMPLES = [
    (
        ROOT / "schemas" / "oqtWorkflowRecord.v1.json",
        ROOT / "schemas" / "examples" / "oqtWorkflowRecord.v1.example.json",
    ),
    (
        ROOT / "schemas" / "oqtHazardEvidenceSummary.v1.json",
        ROOT / "schemas" / "examples" / "oqtHazardEvidenceSummary.v1.example.json",
    ),
    (
        ROOT / "schemas" / "oqtReadAcrossSummary.v1.json",
        ROOT / "schemas" / "examples" / "oqtReadAcrossSummary.v1.example.json",
    ),
    (
        ROOT / "schemas" / "oqtEndpointSummary.v1.json",
        ROOT / "schemas" / "examples" / "oqtEndpointSummary.v1.example.json",
    ),
]


def test_portable_schema_examples_validate():
    for schema_path, example_path in SCHEMA_EXAMPLES:
        schema = _load_json(schema_path)
        example = _load_json(example_path)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(example, schema)


def test_portable_schema_identity_fields_are_stable():
    for schema_path, example_path in SCHEMA_EXAMPLES:
        schema = _load_json(schema_path)
        example = _load_json(example_path)

        assert example["schemaName"] == schema["properties"]["schemaName"]["const"]
        assert (
            example["schemaVersion"] == schema["properties"]["schemaVersion"]["const"]
        )
        assert example["module"] == "oqt-mcp"
