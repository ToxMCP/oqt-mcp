from typing import Any, Dict, Optional


def _clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _first_present(payload: Dict[str, Any], candidates: list[str]) -> Any:
    for candidate in candidates:
        if candidate not in payload:
            continue
        value = _clean_scalar(payload.get(candidate))
        if value not in (None, "", [], {}):
            return value
    return None


def _normalise_additional(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return {
            str(key): value
            for key, value in raw.items()
            if _clean_scalar(value) not in (None, "", [], {})
        } or None

    if isinstance(raw, list):
        items: Dict[str, Any] = {}
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            label = _clean_scalar(
                entry.get("_label") or entry.get("Label") or entry.get("label")
            )
            if not label:
                continue
            value = _clean_scalar(
                entry.get("_value")
                if "_value" in entry
                else entry.get("Value", entry.get("value"))
            )
            items[str(label)] = value
        return items or None

    return None


def parse_metadata_entries(raw: Any) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}

    if isinstance(raw, dict):
        for key, value in raw.items():
            clean_key = _clean_scalar(key)
            clean_value = _clean_scalar(value)
            if clean_key and clean_value not in (None, "", [], {}):
                metadata[str(clean_key)] = clean_value
        return metadata

    if not isinstance(raw, list):
        return metadata

    for entry in raw:
        if isinstance(entry, str):
            if "=" not in entry:
                continue
            key, value = entry.split("=", 1)
            clean_key = _clean_scalar(key)
            clean_value = _clean_scalar(value)
            if clean_key and clean_value not in (None, "", [], {}):
                metadata[str(clean_key)] = clean_value
            continue

        if not isinstance(entry, dict):
            continue
        clean_key = _clean_scalar(
            entry.get("_label") or entry.get("Label") or entry.get("label")
        )
        clean_value = _clean_scalar(
            entry.get("_value")
            if "_value" in entry
            else entry.get("Value", entry.get("value"))
        )
        if clean_key and clean_value not in (None, "", [], {}):
            metadata[str(clean_key)] = clean_value

    return metadata


def build_endpoint_study_record(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    metadata = parse_metadata_entries(payload.get("MetaData"))
    provenance = build_provenance(payload) or {}

    def first_present(*values: Any) -> Any:
        for value in values:
            cleaned = _clean_scalar(value)
            if cleaned not in (None, "", [], {}):
                return cleaned
        return None

    record: Dict[str, Any] = {}
    record_id = first_present(metadata.get("Record ID"), payload.get("Guid"))
    if record_id:
        record["recordId"] = str(record_id)

    endpoint = first_present(payload.get("Endpoint"), metadata.get("Endpoint"))
    if endpoint:
        record["endpoint"] = str(endpoint)

    rigid_path = first_present(payload.get("RigidPath"))
    if rigid_path:
        record["rigidPath"] = str(rigid_path)

    data_type = first_present(payload.get("DataType"))
    if data_type:
        record["dataType"] = str(data_type)

    value = first_present(payload.get("Value"))
    if value is not None:
        record["value"] = value

    unit = first_present(payload.get("Unit"))
    if unit:
        record["unit"] = str(unit)

    qualifier = first_present(payload.get("Qualifier"), metadata.get("Qualifier"))
    if qualifier:
        record["qualifier"] = str(qualifier)

    study = first_present(
        provenance.get("study"), metadata.get("Test type"), metadata.get("Record ID")
    )
    if study:
        record["study"] = str(study)

    citation = first_present(
        provenance.get("citation"),
        metadata.get("Reference source"),
        metadata.get("Database"),
    )
    if citation:
        record["citation"] = str(citation)

    author = first_present(provenance.get("authors"), metadata.get("Author"))
    if author:
        record["author"] = str(author)

    year = first_present(metadata.get("Year"))
    if year:
        record["year"] = str(year)

    test_type = first_present(metadata.get("Test type"))
    if test_type:
        record["testType"] = str(test_type)

    method_type = first_present(metadata.get("Type of method"))
    if method_type:
        record["methodType"] = str(method_type)

    test_organism = first_present(metadata.get("Test organisms (species)"))
    if test_organism:
        record["testOrganism"] = str(test_organism)

    strain = first_present(metadata.get("Strain"))
    if strain:
        record["strain"] = str(strain)

    metabolic_activation = first_present(metadata.get("Metabolic activation"))
    if metabolic_activation:
        record["metabolicActivation"] = str(metabolic_activation)

    overall_result = first_present(metadata.get("OVERALL"))
    if overall_result:
        record["overallResult"] = str(overall_result)

    reference_source = first_present(metadata.get("Reference source"))
    if reference_source:
        record["referenceSource"] = str(reference_source)

    database = first_present(metadata.get("Database"))
    if database:
        record["database"] = str(database)

    if metadata:
        record["metadata"] = metadata

    return record or None


def build_endpoint_study_records(payload: Any) -> list[Dict[str, Any]]:
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    records: list[Dict[str, Any]] = []
    for item in items:
        record = build_endpoint_study_record(item)
        if record:
            records.append(record)
    return records


def build_provenance(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    provenance: Dict[str, Any] = {}

    title = _first_present(payload, ["Title", "Name", "Caption", "_name"])
    if title:
        provenance["title"] = title

    guid = _first_present(payload, ["Guid", "guid"])
    if guid:
        provenance["guid"] = guid

    caption = _first_present(payload, ["Caption"])
    if caption and caption != title:
        provenance["caption"] = caption

    authors = _first_present(payload, ["Authors", "Author", "_authors"])
    if authors:
        provenance["authors"] = authors

    owner = _first_present(payload, ["Owner", "Donator", "_donator", "ModelDeveloper"])
    if owner:
        provenance["owner"] = owner

    description = _first_present(payload, ["Description", "_description"])
    if description:
        provenance["description"] = description

    source_url = _first_present(payload, ["Url", "URL", "_url", "Source"])
    if source_url:
        provenance["source_url"] = source_url

    citation = _first_present(payload, ["Citation"])
    if citation:
        provenance["citation"] = citation

    study = _first_present(payload, ["Study"])
    if study:
        provenance["study"] = study

    disclaimer = _first_present(payload, ["Disclaimer", "_disclaimer"])
    if disclaimer:
        provenance["disclaimer"] = disclaimer

    help_file = _first_present(payload, ["_helpFile", "HelpFile"])
    if help_file:
        provenance["help_file"] = help_file

    position = _first_present(payload, ["Position", "RequestedPosition"])
    if position:
        provenance["position"] = position

    additional = _normalise_additional(
        payload.get("AdditionalInfo", payload.get("_additional"))
    )
    if additional:
        provenance["additional_info"] = additional

    return provenance or None


def _iter_provenance_candidates(payload: Any, *, depth: int = 0):
    if depth > 2:
        return
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            if isinstance(value, (dict, list)):
                yield from _iter_provenance_candidates(value, depth=depth + 1)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                yield from _iter_provenance_candidates(item, depth=depth + 1)


def build_provenance_collection(payload: Any) -> list[Dict[str, Any]]:
    records: list[Dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    for candidate in _iter_provenance_candidates(payload):
        provenance = build_provenance(candidate)
        if not provenance:
            continue
        key = tuple(
            sorted(
                (str(item_key), str(item_value))
                for item_key, item_value in provenance.items()
            )
        )
        if key in seen:
            continue
        seen.add(key)
        records.append(provenance)

    return records


def attach_provenance(
    result: Dict[str, Any],
    payload: Any,
    *,
    field_name: str = "provenance",
) -> Dict[str, Any]:
    provenance = build_provenance(payload)
    if provenance:
        result[field_name] = provenance
    return result


def attach_provenance_collection(
    result: Dict[str, Any],
    payload: Any,
    *,
    field_name: str = "provenance_records",
) -> Dict[str, Any]:
    records = build_provenance_collection(payload)
    if records:
        result[field_name] = records
    return result
