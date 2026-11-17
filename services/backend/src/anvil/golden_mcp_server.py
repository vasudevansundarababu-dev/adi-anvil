"""Pinned MCP1.30 stdio server; no SQL/provider/grade access in this process.

Private inherited pipes establish transport custody. Each discovery/call also
requires an ephemeral session capability and immutable episode-scope hash.
Tool effects are mediated by the bound parent's private Unix gateway, once only.
"""

import hashlib
import json
import os
import secrets
import socket
import stat
from contextlib import closing
from http.client import HTTPConnection
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import anyio
import rfc8785
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError


def hashed(value):
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def read_private(path):
    info = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_size > 65536
    ):
        raise ValueError("Private bounded MCP record required")
    return json.loads(path.read_bytes())


def write_private(path, value):
    raw = rfc8785.dumps(value)
    if len(raw) > 65536:
        raise ValueError("MCP record exceeds bound")
    with open(path, "xb", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def forward(config, home, name, arguments):
    identifier = uuid4().hex
    write_private(
        home / ("request-" + identifier + ".json"),
        {"tool": name, "arguments": arguments, "scope_sha256": config["scope_sha256"]},
    )

    class Unix(HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(65)
            self.sock.connect(config["gateway_socket"])

    with closing(Unix("localhost", timeout=65)) as client:
        client.request(
            "POST",
            "/tool",
            json.dumps({"session_id": identifier}),
            {
                "Authorization": "Bearer " + config["gateway_token"],
                "Content-Type": "application/json",
            },
        )
        response = client.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise ValueError("MCP tool mediator denied; no retry")
        receipt = json.loads(raw)
    value = read_private(home / ("result-" + identifier + ".json"))
    if receipt != {"sha256": hashed(value)}:
        raise ValueError("MCP tool result changed")
    return value


async def main():
    if version("mcp") != "1.30.0":
        raise ValueError("Pinned MCP1.30.0 required")
    if any(
        v and ("DATABASE" in k or k.endswith("API_KEY") or k.endswith("PRIVATE_KEY"))
        for k, v in os.environ.items()
    ):
        raise ValueError("MCP server must not inherit SQL/provider credentials")
    path = Path(os.environ["ANVIL_MCP_CONFIG_FILE"])
    home = path.parent
    info = home.lstat()
    if (
        not path.is_absolute()
        or home.resolve() != home
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Private canonical MCP session required")
    config = read_private(path)
    if config["scope_sha256"] != hashed(config["scope"]):
        raise ValueError("MCP episode scope changed")
    tools = [types.Tool.model_validate(t) for t in config["tools"]]
    known = {t.name for t in tools}
    if len(known) != len(tools) or not 1 <= len(tools) <= 50:
        raise ValueError("Bounded unique MCP tool catalogue required")
    server = Server("anvil-role-scoped-mcp", version="1")

    def authorize():
        meta = server.request_context.meta
        values = meta.model_dump(exclude_none=True) if meta is not None else {}
        if (
            set(values) != {"anvil_session", "scope_sha256"}
            or type(values.get("anvil_session")) is not str
            or not secrets.compare_digest(values["anvil_session"], config["session_capability"])
            or values.get("scope_sha256") != config["scope_sha256"]
        ):
            raise McpError(types.ErrorData(code=-32001, message="MCP session scope denied"))

    @server.list_tools()
    async def list_tools():
        authorize()
        return tools

    @server.call_tool(validate_input=True)
    async def call_tool(name, arguments):
        authorize()
        if (
            name not in known
            or not isinstance(arguments, dict)
            or len(rfc8785.dumps(arguments)) > 32768
        ):
            raise McpError(
                types.ErrorData(code=-32602, message="Bounded declared MCP tool required")
            )
        try:
            value = await anyio.to_thread.run_sync(forward, config, home, name, arguments)
        except (OSError, ValueError, KeyError):
            raise McpError(
                types.ErrorData(code=-32002, message="MCP tool denied; no automatic retry")
            ) from None
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(value))],
            structuredContent=value,
        )

    class BoundedInput:
        def __aiter__(self):
            return self

        async def __anext__(self):
            import sys

            line = await anyio.to_thread.run_sync(sys.stdin.buffer.readline, 65537)
            if not line:
                raise StopAsyncIteration
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise ValueError("Bounded newline-framed MCP request required")
            return line.decode("utf-8")

    async with stdio_server(stdin=BoundedInput()) as (incoming, outgoing):
        await server.run(incoming, outgoing, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
