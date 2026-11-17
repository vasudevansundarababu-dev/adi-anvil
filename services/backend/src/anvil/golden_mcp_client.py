"""Actual MCP SDK stdio client for the bound trusted OpenEnv tool mediator.

The model gets public tool schemas and observations, never capabilities, pipes,
SQL credentials, expected answers or an independently spendable provider client.
"""

import re
import secrets
import sys
import tempfile
import threading
from contextlib import AsyncExitStack
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import anyio
from anyio.from_thread import start_blocking_portal
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from anvil.golden_kyc_tool_contract import tools
from anvil.marketing_native_mcp_support import (
    ROOT,
    NativeGateway,
    owned_json,
    private_json,
    schema_check,
)
from anvil.praxis_generic_contract import digest


class McpEpisode:
    def __init__(
        self,
        episode,
        scope,
        guard,
        *,
        public_tools=None,
        action_factory=None,
        contract="golden-kyc-v2",
        before_effect=None,
    ):
        self.episode, self.scope, self.guard = episode, deepcopy(scope), guard
        if scope.get("generation") != episode.credentials["generation"]:
            raise ValueError("MCP scope must bind the current episode generation")
        self.credentials = episode.credentials
        self.home = Path(tempfile.mkdtemp(prefix="anvil-mcp-", dir="/tmp")).resolve()
        self.scope_hash = digest(scope)
        if contract not in {"golden-kyc-v2", "marketing-task2-v3"}:
            raise ValueError("Qualified Anvil-owned MCP domain contract required")
        self.contract = contract
        if before_effect is not None and (
            contract != "marketing-task2-v3" or not callable(before_effect)
        ):
            raise ValueError("Trusted Marketing before-effect hook required")
        self.before_effect = before_effect
        self.action_factory = action_factory
        self.public_tools = deepcopy(public_tools) if public_tools is not None else tools()
        self.by_name = {t["id"]: t for t in self.public_tools}
        self.calls = []
        self.session_capability = secrets.token_urlsafe(32)
        self.gateway = NativeGateway(self.home, self._effect, socket_root=self.home)
        self.catalogue = [
            {
                "name": t["id"],
                "description": "Bound Golden KYC tool; runtime schema version2"
                if contract == "golden-kyc-v2"
                else "Bound Marketing Task2 tool; exact graph role permissions",
                "inputSchema": t["input_schema"],
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "result": t["output_schema"],
                        "done": {"type": "boolean"},
                        "generation": {"type": "integer"},
                    },
                    "required": ["result", "done", "generation"],
                    "additionalProperties": False,
                },
            }
            for t in self.public_tools
        ]
        private_json(
            self.home / "configuration.json",
            {
                "scope": scope,
                "scope_sha256": self.scope_hash,
                "session_capability": self.session_capability,
                "tools": self.catalogue,
                "gateway_socket": self.gateway.path,
                "gateway_token": self.gateway.token,
            },
        )
        self.portal_context = None
        self.portal = None
        self.ready = threading.Event()
        self.service_error = None

    def _effect(self, route, identifier, consumed):
        if (
            route != "/tool"
            or type(identifier) is not str
            or not re.fullmatch(r"[a-f0-9]{32}", identifier)
            or identifier in consumed
        ):
            raise ValueError("MCP effect correlation denied")
        value = owned_json(self.home, "request-" + identifier + ".json")
        if (
            set(value) != {"tool", "arguments", "scope_sha256"}
            or value["scope_sha256"] != self.scope_hash
            or value["tool"] not in self.by_name
            or not self.guard()
            or self.episode.credentials["generation"] != self.scope["generation"]
        ):
            raise ValueError("MCP scope or current runtime authorization denied")
        schema_check(value["arguments"], self.by_name[value["tool"]]["input_schema"])
        consumed[identifier] = {"started": True}
        private_json(
            self.home / ("effect-" + identifier + ".json"),
            {"input_sha256": digest(value), "scope_sha256": self.scope_hash},
        )
        factory = self.action_factory
        if factory is None:
            from anvil.golden_kyc_openenv import GoldenAction

            factory = GoldenAction

        correlated = {"request_id": identifier} if self.contract == "marketing-task2-v3" else {}
        if self.before_effect is not None:
            # The trusted host commits one-way intent before actual OpenEnv IO.
            # A failed/ambiguous hook never reaches or retries the tool effect.
            self.before_effect(identifier, value["tool"], deepcopy(value["arguments"]))
        observed = self.episode.step(
            factory(
                operation=value["tool"],
                arguments=value["arguments"],
                expected_generation=self.scope["generation"],
                **correlated,
            )
        )
        result = {
            "result": observed.result,
            "done": observed.done,
            "generation": self.scope["generation"],
        }
        private_json(self.home / ("result-" + identifier + ".json"), result)
        self.calls.append(
            {
                "effect_id": identifier,
                "tool": value["tool"],
                "input_sha256": digest(value),
                "result_sha256": digest(result),
            }
        )
        return {"sha256": digest(result)}

    @property
    def meta(self):
        return {"anvil_session": self.session_capability, "scope_sha256": self.scope_hash}

    async def _open_session(self, stack):
        self.stderr = open(self.home / "server-private.log", "x")
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self.home),
            "PYTHONPATH": str(ROOT / "services/backend/src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "ANVIL_MCP_CONFIG_FILE": str(self.home / "configuration.json"),
        }
        streams = await stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=sys.executable, args=["-m", "anvil.golden_mcp_server"], env=env
                ),
                errlog=self.stderr,
            )
        )
        self.session = await stack.enter_async_context(
            ClientSession(*streams, read_timeout_seconds=timedelta(seconds=65))
        )
        initialized = await self.session.initialize()
        self.protocol_version = initialized.protocolVersion
        discovered = await self.session.list_tools(
            params=types.PaginatedRequestParams(**{"_meta": self.meta})
        )
        actual = [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema,
                "outputSchema": t.outputSchema,
            }
            for t in discovered.tools
        ]
        if digest(actual) != digest(self.catalogue):
            raise ValueError("Actual MCP discovery differs from the bound versioned tool schemas")

    async def _serve(self):
        try:
            self.stop = anyio.Event()
            async with AsyncExitStack() as stack:
                await self._open_session(stack)
                self.ready.set()
                await self.stop.wait()
        except BaseException as exc:
            self.service_error = exc
        finally:
            self.ready.set()
            if hasattr(self, "stderr"):
                self.stderr.close()

    def __enter__(self):
        self.portal_context = start_blocking_portal()
        self.portal = self.portal_context.__enter__()
        try:
            self.service = self.portal.start_task_soon(self._serve)
            if not self.ready.wait(65):
                raise RuntimeError("MCP handshake timed out; no retry")
            if self.service_error is not None:
                raise RuntimeError(
                    "MCP handshake failed; inspect private session log"
                ) from self.service_error
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *exc):
        try:
            if self.portal is not None:
                if hasattr(self, "stop"):
                    self.portal.call(self.stop.set)
                self.service.result(timeout=10)
        finally:
            if self.portal_context is not None:
                self.portal_context.__exit__(*exc)
            self.gateway.close()

    def step(self, action):
        if (
            action.expected_generation != self.scope["generation"]
            or self.episode.credentials["generation"] != self.scope["generation"]
            or not self.guard()
            or self.gateway.error
        ):
            raise ValueError("MCP generation or current native authority changed")

        async def call():
            return await self.session.call_tool(action.operation, action.arguments, meta=self.meta)

        response = self.portal.call(call)
        if response.isError or not isinstance(response.structuredContent, dict):
            raise ValueError("MCP tool returned an error; no automatic retry")
        value = response.structuredContent
        if (
            set(value) != {"result", "done", "generation"}
            or value["generation"] != self.scope["generation"]
        ):
            raise ValueError("MCP result envelope or generation changed")
        return SimpleNamespace(result=value["result"], done=value["done"])

    def public_receipt(self):
        return {
            "adapter": "anvil-golden-mcp-stdio-v1"
            if self.contract == "golden-kyc-v2"
            else "anvil-marketing-task2-mcp-stdio-v1",
            "domain_contract": self.contract,
            "sdk_version": "1.30.0",
            "protocol_version": self.protocol_version,
            "scope_sha256": self.scope_hash,
            "tool_catalogue_sha256": digest(self.catalogue),
            "tool_effects": self.calls.copy(),
            "provider_credentials_to_server": False,
            "database_credentials_to_server": False,
        }
