# O-QT MCP Server - Timeout & Compatibility Fix Summary

## Overview

This document summarizes the fixes applied to resolve timeout issues and improve compatibility with Codex CLI and other MCP clients.

## Problems Addressed

1. **60-Second Timeout Errors**: Heavy QSAR operations were timing out before completion
2. **404 Error Handling**: Poor error messages when chemical/endpoint data was unavailable
3. **MCP Content Type Issues**: Non-standard JSON content type causing validation errors

## Solutions Implemented

### 1. Extended Timeout Configuration

**Changes:**
- Server-side heavy timeout: 120s → 300s (5 minutes)
- Codex CLI timeout configuration: Added 300-second timeout
- Improved connection/write timeouts for heavy operations

**Files Modified:**
- `o-qt-mcp-server/src/qsar/client.py`
- `../.codex/config.toml`

**Impact:**
All heavy operations (workflows, metabolism, reports) can now complete successfully within the 5-minute window.

### 2. Improved Error Handling

**Changes:**
- Enhanced `analyze_chemical_hazard` with better 404 error messages
- Added data availability tracking
- Included actionable suggestions when data is missing

**Files Modified:**
- `o-qt-mcp-server/src/tools/implementations/o_qt_qsar_tools.py`

**Impact:**
Users now receive clear guidance when data is unavailable, including:
- Why the data might be missing
- Alternative identifiers to try (CAS, SMILES, name)
- Next steps for troubleshooting

### 3. MCP Content Type Standardization

**Changes:**
- Standardized tool responses to use `text` content type
- JSON data is now serialized as formatted text
- Maintained backward compatibility

**Files Modified:**
- `o-qt-mcp-server/src/mcp/router.py`

**Impact:**
- Resolves Zod validation errors in Codex CLI
- Ensures MCP specification compliance
- Works with all MCP clients (Codex, Gemini, Claude Desktop)

## Testing Instructions

### 1. Restart the MCP Server

```bash
cd o-qt-mcp-server
lsof -ti:8000 | xargs kill -9 2>/dev/null
poetry run uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Restart Codex CLI

After updating `.codex/config.toml`, restart Codex to pick up the new timeout configuration:

```bash
# Close and reopen Codex CLI
```

### 3. Test Heavy Operations

Try these previously failing operations in Codex CLI:

```bash
# Test 1: Metabolism Simulation
"Can you use oqt-mcp to generate metabolites for acetaminophen (SMILES: CC(=O)Nc1ccc(O)cc1) using the Liver simulator?"

# Test 2: Workflow Execution
"Can you use oqt-mcp to execute a workflow for benzene?"

# Test 3: QSAR Report Generation
"Can you use oqt-mcp to download a QSAR report for acetaminophen?"

# Test 4: Chemical Profiling
"Can you use oqt-mcp to run profiling for acetaminophen?"
```

### 4. Test Error Handling

```bash
# Test with a chemical that may not have data
"Can you use oqt-mcp to analyze chemical hazard for 'test-chemical-123' for the endpoint 'Skin Sensitization'?"
```

Expected: Clear error message with suggestions, not a generic 404 error.

### 5. Verify Discovery Tools Still Work

```bash
# Quick verification
"Can you use oqt-mcp to search for acetaminophen?"
"Can you use oqt-mcp to list available profilers?"
```

## Expected Results

### ✅ Success Indicators

1. **No more timeout errors** for operations taking 1-5 minutes
2. **Clear error messages** when data is unavailable (404s)
3. **No Zod validation errors** in Codex CLI
4. **All discovery tools** continue to work normally
5. **Backward compatibility** maintained with other MCP clients

### ⚠️ Known Limitations

1. **5-Minute Maximum**: Operations taking longer than 5 minutes will still timeout
   - If this occurs, consider breaking the operation into smaller steps
   - Or contact the QSAR Toolbox API team about performance

2. **Data Availability**: Some chemicals may not have data for all endpoints
   - This is a data limitation, not a technical issue
   - The improved error messages will guide users to alternatives

## Rollback Instructions

If issues occur, you can rollback the changes:

### 1. Revert Timeout Changes

```bash
cd o-qt-mcp-server
git checkout HEAD -- src/qsar/client.py
```

### 2. Remove Codex Timeout Configuration

Edit `../.codex/config.toml` and remove the timeout line:

```toml
[mcp_servers.oqt-mcp]
url = "http://localhost:8000/mcp"
# Remove this line: timeout = 300000
```

### 3. Restart Server

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null
poetry run uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

## Support

If you encounter issues after applying these fixes:

1. Check the server logs for detailed error messages
2. Verify the MCP server is running on port 8000
3. Confirm Codex CLI has been restarted after config changes
4. Review the detailed documentation in `docs/MCP_CLIENT_COMPATIBILITY_FIX.md`

## Next Steps

1. **Monitor Performance**: Track operation completion times
2. **Gather Feedback**: Collect user feedback on error messages
3. **Optimize Further**: If 5 minutes is still insufficient for some operations, consider:
   - Implementing async job patterns
   - Adding progress indicators
   - Caching frequently-used results

## Change Log

- **2025-01-04**: Initial timeout and compatibility fixes implemented
  - Extended server timeout to 300s
  - Added Codex CLI timeout configuration
  - Improved error handling for 404 responses
  - Standardized MCP content types
