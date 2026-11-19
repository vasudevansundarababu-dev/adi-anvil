# Isolated MCP source candidate

The additive v3 nomination binds the current isolated `golden_mcp_client.py`
source. It preserves v1/v2 modules and JSON nominations byte-for-byte; the only
graph-source pin change from v2 is the MCP client. The candidate JSON explicitly
retains `native_qualified: false` and the predecessor manifest hash.

Current source comparison and new world-nomination checks select v3. Existing
retained private `component-context-intent.v3` contexts keep their prior v2
nomination; they are never reinterpreted as v3 candidates. Original private
program hash reconciliation remains required. Unknown context schemas refuse.

This is source consistency only. It neither approves old contexts nor supplies
new versioned context identity, independent evidence, native qualification or
paid authority. New native execution remains closed until a separately bound
context protocol and the independent producer closure qualify the successor.
Changing current file pins cannot migrate retained execution contexts.
