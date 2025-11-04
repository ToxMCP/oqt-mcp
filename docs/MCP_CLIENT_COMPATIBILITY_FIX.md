# MCP Client Compatibility & Timeout Fix

## Issue Summary

The O-QT MCP Server was experiencing two major issues with Codex CLI:

1. **Zod Validation Errors**: Compatibility issues resulting in:
   ```
   "Invalid literal value, expected \"resource_link\""
   "Invalid literal value, expected \"resource\""
   ```

2. **60-Second Timeout Errors**: Long-running QSAR operations (workflows, metabolism simulations, report generation) were hitting the MCP client's 60-second timeout, even though the operations could take 2-5 minutes to complete.

## Root Causes

### 1. Non-Standard Content Type

The server was returning tool responses with a non-standard MCP content type:

```json
{
  "content": [
    {
      "type": "json",
      "json": { ... }
    }
  ]
}
```

However, the MCP specification only defines these standard content types:
- `text` - for text content
- `image` - for image content
- `resource` - for resource references
- `resource_link` - for resource links

Codex and Gemini CLI strictly validate against these types and reject `"type": "json"`.

### 2. Timeout Mismatches

- **MCP Client Timeout**: Codex CLI enforces a default 60-second timeout for all MCP tool calls
- **QSAR API Operations**: Heavy operations (workflows, metabolism, reports) can take 2-5 minutes
- **Server Timeout**: The server's heavy profile was set to 120 seconds, which was insufficient for the longest operations

## Solutions Implemented

### Fix 1: Content Type Standardization

Modified `src/mcp/router.py` to return tool results as `text` content with JSON-serialized data:

```python
return {
    "content": [
        {
            "type": "text",
            "text": json.dumps(result, indent=2, ensure_ascii=False),
        }
    ]
}
```

### Fix 2: Extended Timeout Configuration

**Server-Side Changes** (`src/qsar/client.py`):
- Increased heavy timeout profile from 120s to 300s (5 minutes)
- Updated timeout configuration:
  ```python
  "heavy": httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=15.0)
  ```

**Client-Side Changes** (`.codex/config.toml`):
- Added explicit timeout configuration for Codex CLI:
  ```toml
  [mcp_servers.oqt-mcp]
  url = "http://localhost:8000/mcp"
  timeout = 300000  # 5 minutes in milliseconds
  ```

### Fix 3: Improved Error Handling

Enhanced `analyze_chemical_hazard` tool to provide better feedback for 404 errors:
- Clear warnings when endpoint/profiling data is not available
- Helpful suggestions for alternative identifiers (CAS, SMILES, name)
- Data availability tracking in response
- Actionable next steps when data is missing

## Changes Made

### Content Type Fix
1. **Added JSON import** to `router.py`
2. **Updated `handle_call_tool` function** to serialize results as formatted JSON text
3. **Maintained backward compatibility** - tools that already return MCP-formatted content are passed through unchanged

### Timeout Fixes
1. **Extended server-side heavy timeout** from 120s to 300s in `QsarClient`
2. **Added Codex MCP timeout configuration** (300 seconds) in `.codex/config.toml`
3. **Improved connection timeouts** for heavy operations (10s connect, 60s write)

### Error Handling Improvements
1. **Enhanced 404 error messages** with context-specific guidance
2. **Added data availability tracking** to hazard analysis responses
3. **Included actionable suggestions** when data is not found

## Testing

### Verify Server Response Format

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "search_chemicals",
      "arguments": {
        "query": "acetaminophen",
        "search_type": "name"
      }
    },
    "id": 1
  }' | jq '.result.content[0].type'
```

Expected output: `"text"`

### Test with Codex CLI

```bash
# In Codex CLI
can you use oqt mcp and search for acetaminophen?
```

### Test with Gemini CLI

```bash
# In Gemini CLI
> can you use oqt mcp and run acetaminophen?
```

### Test with Claude Desktop (Cline)

The fix maintains compatibility with Claude Desktop and other MCP clients that may have been working previously.

## Expected Outcomes

After implementing these fixes, the following tools should now work correctly in Codex CLI:

### ✅ Working Tools (Previously Timing Out)
- `generate_metabolites` - Metabolism simulation (now completes within 5 min)
- `run_oqt_multiagent_workflow` - Multi-agent workflows (now completes within 5 min)
- `run_qsar_workflow` - QSAR workflows (now completes within 5 min)
- `run_qsar_model` - QSAR model execution (now completes within 5 min)
- `run_profiler` - Chemical profiling (now completes within 5 min)
- `run_metabolism_simulator` - Metabolism simulation (now completes within 5 min)
- `download_qmrf` - QMRF report generation (now completes within 5 min)
- `download_qsar_report` - QSAR report generation (now completes within 5 min)
- `execute_workflow` - Workflow execution (now completes within 5 min)
- `download_workflow_report` - Workflow report generation (now completes within 5 min)
- `group_chemicals_by_profiler` - Chemical grouping (now completes within 5 min)
- `canonicalize_structure` - Structure canonicalization (now completes within 5 min)
- `structure_connectivity` - Connectivity analysis (now completes within 5 min)
- `render_pdf_from_log` - PDF generation (now completes within 5 min)

### ✅ Improved Error Handling
- `analyze_chemical_hazard` - Now provides clear guidance when data is unavailable (404 errors)
  - Explains why data might be missing
  - Suggests alternative identifiers to try
  - Includes data availability status in response

### ✅ Already Working (Discovery Tools)
- `list_profilers` - Lists available profilers
- `get_profiler_info` - Gets profiler metadata
- `list_simulators` - Lists metabolism simulators
- `get_simulator_info` - Gets simulator metadata
- `list_calculators` - Lists available calculators
- `get_calculator_info` - Gets calculator metadata
- `get_endpoint_tree` - Gets endpoint hierarchy
- `get_metadata_hierarchy` - Gets metadata structure
- `list_qsar_models` - Lists QSAR models
- `list_all_qsar_models` - Lists all QSAR models
- `search_chemicals` - Searches for chemicals
- `get_public_qsar_model_info` - Gets QSAR model info
- `run_qsar_prediction` - Runs QSAR predictions
- `list_search_databases` - Lists search databases

## Benefits

✅ **Codex CLI compatibility** - No more Zod validation errors  
✅ **Gemini CLI compatibility** - Proper content type recognition  
✅ **Extended timeout support** - Heavy operations can now complete (up to 5 minutes)  
✅ **Better error messages** - Clear guidance when data is unavailable  
✅ **Backward compatibility** - Existing clients continue to work  
✅ **Standards compliance** - Adheres to MCP specification  
✅ **Human-readable** - JSON is formatted with indentation for readability

## Files Modified

- `o-qt-mcp-server/src/mcp/router.py` - Content type standardization
- `o-qt-mcp-server/src/qsar/client.py` - Extended timeout profiles
- `o-qt-mcp-server/src/tools/implementations/o_qt_qsar_tools.py` - Improved error handling
- `../.codex/config.toml` - Added MCP timeout configuration

## Deployment

1. Stop the running MCP server
2. Pull the latest changes
3. Restart the server:

```bash
cd o-qt-mcp-server
lsof -ti:8000 | xargs kill -9 2>/dev/null
poetry run uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

## Related Documentation

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [MCP Content Types](https://spec.modelcontextprotocol.io/specification/basic/messages/#content)
