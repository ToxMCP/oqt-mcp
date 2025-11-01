# Toolbox WebAPI Coverage – Stakeholder Review Notes

Prepared for: O-QT assistant team  
Objective: validate that our current MCP tool roadmap aligns with Toolbox WebAPI capabilities and identify missing endpoints or operational constraints.

## Summary Talking Points

1. **Tool Coverage**
   - Confirm that planned MCP tools (`get_public_qsar_model_info`, `search_chemicals`, `run_qsar_prediction`, `analyze_chemical_hazard`, `generate_metabolites`) map cleanly onto available WebAPI endpoints (see `docs/toolbox_webapi_overview.md`).
   - Discuss appetite for additional tools (calculators, workflow execution, IUCLID lookups) and associated RBAC requirements.

2. **Authentication & Sessions**
   - Clarify whether Toolbox endpoints require session tokens or API keys beyond OAuth; align on headers/cookies needed.
   - Confirm expected rate limits and policies for external MCP clients.

3. **Performance Considerations**
   - Long-running operations (profiling, workflows) – do they return task IDs? Decide on polling vs. asynchronous MCP patterns.
   - Data-heavy endpoints (`/data`, `/grouping`) – agree on pagination/limits to avoid overwhelming the MCP channel.

4. **Response Shape Stability**
   - Validate JSON structures used in `docs/toolbox_webapi_samples.md` against production responses.
   - Identify fields that are optional or subject to change so we can design resilient Pydantic models.

5. **Security & RBAC**
   - Map Toolbox privilege levels to MCP role definitions (Guest/Researcher/Lab Admin).
   - Decide if any endpoints require elevated “system” roles or off-limits to conversational agents.

## Questions to Resolve

1. Are there endpoints we must integrate for MVP that are not in the current tool list?
2. Do we need to support Toolbox-specific error codes/messages in MCP results?
3. Should we expose calculator enumeration/apply flows in the first release?
4. What is the expected frequency of metabolite simulations and QSAR predictions (helps tune timeouts/backoff)?

## Next Steps After Review

* Update Task 4 subtasks based on newly prioritised endpoints or data fields.
* Adjust RBAC and auth tasks (Tasks 2 & 3) if stakeholder input changes claim sources or role mappings.
* Capture any new tasks in Taskmaster (e.g., additional logging, workflow support) as follow-up items.
