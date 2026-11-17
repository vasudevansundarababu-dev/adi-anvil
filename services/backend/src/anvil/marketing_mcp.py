"""Real MCP1.30 role catalogue over a host-bound Marketing OpenEnv session."""

from anvil.db import digest
from anvil.golden_mcp_client import McpEpisode
from anvil.marketing_task2_openenv import MarketingNativeAction
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.praxis_marketing_contract import MarketingExecution


class MarketingMcpEpisode(McpEpisode):
    def __init__(self, episode, scope, guard, execution, *, before_effect=None):
        contract = MarketingExecution.model_validate(execution)
        if (
            scope.get("role") != episode.role
            or scope.get("workflow_graph_sha256") != contract.workflow_graph_sha256
            or scope.get("schema_version") != "anvil.marketing-mcp-scope.v1"
            or getattr(episode, "execution_sha256", None) != wire_digest(contract.model_dump())
            or (
                episode.source_refs
                and scope.get("input_refs_sha256") != digest(episode.source_refs)
            )
        ):
            raise ValueError("Exact Marketing role and frozen graph scope required")
        public = [
            {
                "id": tool.id,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "error_schema": tool.error_schema,
            }
            for tool in contract.tools
            if episode.role in tool.role_ids
        ]
        super().__init__(
            episode,
            scope,
            guard,
            public_tools=public,
            action_factory=MarketingNativeAction,
            contract="marketing-task2-v3",
            before_effect=before_effect,
        )
