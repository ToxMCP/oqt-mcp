from src.utils.privacy import scrub_dict, scrub_value


def test_scrub_value_hashes_smiles():
    result = scrub_value("smiles", "CCO")
    assert result.startswith("[HASH:")


def test_scrub_value_hashes_cas():
    result = scrub_value("cas", "50-00-0")
    assert result.startswith("[HASH:")


def test_scrub_value_heuristic_smiles():
    # Heuristic detection even for generic keys
    result = scrub_value("query", "c1ccccc1")
    assert result.startswith("[HASH:")


def test_scrub_value_leaves_safe_data():
    result = scrub_value("model_id", "model-123")
    assert result == "model-123"


def test_scrub_dict_scrubs_nested_values():
    params = {
        "smiles": "CCO",
        "model_id": "model-123",
        "nested": {"chemical_name": "Ethanol"},
        "llm_api_key": "sk-secret",
    }
    scrubbed = scrub_dict(params)
    assert scrubbed["smiles"].startswith("[HASH:")
    assert scrubbed["model_id"] == "model-123"
    assert scrubbed["nested"]["chemical_name"].startswith("[HASH:")
    assert scrubbed["llm_api_key"].startswith("[HASH:")
