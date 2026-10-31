"""One bounded, server-mediated JSON response per admitted Harbor stage."""

import base64
import http.client
import json
import os
import socket
from contextlib import closing

from harbor.agents.base import BaseAgent


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=100)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class StructuredAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_index = 0

    @staticmethod
    def name():
        return "anvil-structured-json-v1"

    def version(self):
        return "1.0.0"

    async def setup(self, environment):
        return

    async def run(self, instruction, environment, context):
        # The host mediator reconstructs only admitted actor material and authoritative state.
        # This adapter never opens task_dir, a reference solution, a rubric or future evidence.
        path = os.environ["ANVIL_HARBOR_GATEWAY_SOCKET"]
        token = os.environ["ANVIL_HARBOR_GATEWAY_TOKEN"]
        with closing(UnixConnection(path)) as connection:
            connection.request(
                "POST",
                "/decision",
                json.dumps({"stage_index": self.stage_index}),
                {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            data = response.read(65537)
            if response.status != 200 or len(data) > 65536:
                raise RuntimeError("Gateway blocked or dispatch unknown; no automatic retry")
        output = json.loads(data)["output"]
        if not isinstance(output, (dict, str)):
            raise RuntimeError("Expected admitted response data")
        text = output if isinstance(output, str) else json.dumps(output, allow_nan=False)
        payload = base64.b64encode(text.encode()).decode()
        # Base64 is data inside a fixed command, never a generated shell/program from model text.
        command = (
            "python3 -c \"import base64;from pathlib import Path;Path('/workspace/output.json').write_bytes(base64.b64decode('"
            + payload
            + "'))\""
        )
        result = await environment.exec(command=command, timeout_sec=10)
        if result.return_code != 0:
            raise RuntimeError("Unable to write admitted JSON output")
        self.stage_index += 1
