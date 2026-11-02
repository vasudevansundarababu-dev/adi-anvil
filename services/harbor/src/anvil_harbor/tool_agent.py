"""Trusted host adapter. Candidate actions/tool execution stay at the guarded mediator."""

import json
import os
from contextlib import closing

from harbor.agents.base import BaseAgent

from anvil_harbor.agent import UnixConnection


class ToolAgent(BaseAgent):
    @staticmethod
    def name():
        return "anvil-mcp-tool-agent-v1"

    def version(self):
        return "1.0.0"

    async def setup(self, environment):
        return

    async def run(self, instruction, environment, context):
        # session_id is Harbor's trusted host object, never a candidate-supplied parameter.
        with closing(UnixConnection(os.environ["ANVIL_HARBOR_GATEWAY_SOCKET"])) as connection:
            connection.timeout = 600
            connection.request(
                "POST",
                "/execute",
                json.dumps({"session_id": environment.session_id}),
                {
                    "Authorization": "Bearer " + os.environ["ANVIL_HARBOR_GATEWAY_TOKEN"],
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            data = response.read(65537)
            if response.status != 200 or len(data) > 65536:
                raise RuntimeError("Tool execution blocked or unknown; no automatic retry")
            if json.loads(data).get("status") != "completed":
                raise RuntimeError("Tool execution did not complete")
