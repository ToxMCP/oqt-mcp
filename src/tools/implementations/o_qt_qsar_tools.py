import logging
from pydantic import BaseModel, Field

from src.tools.registry import tool_registry
from src.qsar import qsar_client, QsarClientError

log = logging.getLogger(__name__)

# --- Pydantic Models for Tool Parameters (Input Validation - Section 2.3) ---

class ModelInfoParams(BaseModel):
    model_id: str = Field(..., description="The unique identifier for the QSAR model.")

class ChemicalSearchParams(BaseModel):
    query: str = Field(..., description="The search term (Name, CAS number, or SMILES).")
    search_type: str = Field("auto", description="Type of search (e.g., 'auto', 'name', 'cas', 'smiles').")

class QSARPredictionParams(BaseModel):
    smiles: str = Field(..., description="The SMILES representation of the chemical structure.")
    model_id: str = Field(..., description="The identifier of the QSAR model to use for prediction.")

class HazardAnalysisParams(BaseModel):
    chemical_identifier: str = Field(..., description="CAS number or SMILES of the chemical.")
    endpoint: str = Field(..., description="The toxicological endpoint to analyze (e.g., 'Skin Sensitization', 'Mutagenicity').")

class MetabolismParams(BaseModel):
    smiles: str = Field(..., description="The SMILES representation of the chemical structure.")
    simulator: str = Field(..., description="The metabolism simulator to use (e.g., 'Liver', 'Skin', 'Microbial').")


# --- Tool Implementations ---
# These functions contain the actual logic for interacting with the O-QT QSAR Toolbox.

async def get_public_qsar_model_info(model_id: str) -> dict:
    """Retrieves information about a specific QSAR model."""
    log.info(f"Fetching QSAR model info for ID: {model_id}")
    try:
        return await qsar_client.get_model_metadata(model_id)
    except QsarClientError as exc:
        log.error("Failed to retrieve QSAR model info: %s", exc)
        raise

async def search_chemicals(query: str, search_type: str) -> dict:
    """Searches for a chemical in the QSAR Toolbox database."""
    log.info(f"Searching chemical: {query} (Type: {search_type})")
    try:
        return await qsar_client.search_chemicals(query, search_type)
    except QsarClientError as exc:
        log.error("Chemical search failed: %s", exc)
        raise

async def run_qsar_prediction(smiles: str, model_id: str) -> dict:
    """Runs a QSAR prediction."""
    log.info(f"Running QSAR prediction for SMILES: {smiles[:20]}... using model: {model_id}")

    try:
        prediction = await qsar_client.run_prediction(smiles, model_id)
        return prediction
    except QsarClientError as exc:
        log.error("QSAR prediction failed: %s", exc)
        raise

async def analyze_chemical_hazard(chemical_identifier: str, endpoint: str) -> dict:
    """Analyzes hazards by fetching experimental data and profiling."""
    log.info(f"Analyzing hazard for {chemical_identifier} regarding {endpoint}")

    try:
        endpoint_data = await qsar_client.get_endpoint_data(chemical_identifier, endpoint)
        profiling = await qsar_client.profile_chemical(chemical_identifier)
    except QsarClientError as exc:
        log.error("Hazard analysis failed: %s", exc)
        raise

    summary = {
        "chemical_identifier": chemical_identifier,
        "endpoint": endpoint,
        "endpoint_data": endpoint_data,
        "profiling": profiling,
    }
    return summary

async def generate_metabolites(smiles: str, simulator: str) -> dict:
    """Simulates metabolism for a given chemical structure."""
    log.info(f"Generating metabolites for {smiles[:20]}... using simulator: {simulator}")
    try:
        return await qsar_client.generate_metabolites(smiles, simulator)
    except QsarClientError as exc:
        log.error("Metabolite generation failed: %s", exc)
        raise


# --- Tool Registration ---

def register_qsar_tools():
    """Registers the O-QT QSAR tools with the tool registry."""

    tool_registry.register(
        name="get_public_qsar_model_info",
        # Descriptions are critical for LLM understanding (Section 3.1)
        description="Retrieves metadata and status information for a specified public QSAR model from the O-QT Toolbox.",
        parameters_model=ModelInfoParams,
        implementation=get_public_qsar_model_info
    )

    tool_registry.register(
        name="search_chemicals",
        description="Searches the QSAR Toolbox database for chemical structures by name, CAS number, or SMILES.",
        parameters_model=ChemicalSearchParams,
        implementation=search_chemicals
    )

    tool_registry.register(
        name="run_qsar_prediction",
        description="Executes a QSAR prediction for a chemical structure (SMILES string) using a specified model.",
        parameters_model=QSARPredictionParams,
        implementation=run_qsar_prediction
    )

    tool_registry.register(
        name="analyze_chemical_hazard",
        description="Performs a hazard analysis by fetching experimental data and running profilers for a specific toxicological endpoint.",
        parameters_model=HazardAnalysisParams,
        implementation=analyze_chemical_hazard
    )
    
    tool_registry.register(
        name="generate_metabolites",
        description="Simulates the metabolism of a chemical structure using a specified simulator (e.g., Liver, Skin).",
        parameters_model=MetabolismParams,
        implementation=generate_metabolites
    )

# Register tools upon import
register_qsar_tools()
