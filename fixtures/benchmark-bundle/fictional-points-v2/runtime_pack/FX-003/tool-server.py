"""Original arithmetic fixture MCP server; software conformance only."""
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    identifier = request.get("id")
    if identifier is None:
        continue
    method = request.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "fictional-arithmetic", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "square", "description": "Square a fixture integer",
                  "inputSchema": {"type": "object", "properties": {"n": {"type": "integer",
                                  "minimum": 1, "maximum": 1000}}, "required": ["n"],
                                  "additionalProperties": False}}]}
    elif method == "tools/call":
        params = request["params"]
        args = params.get("arguments", {})
        if params.get("name") != "square" or set(args) != {"n"} or type(args["n"]) is not int or not 1 <= args["n"] <= 1000:
            result = {"content": [{"type": "text", "text": "invalid arithmetic request"}], "isError": True}
        else:
            result = {"content": [{"type": "text", "text": str(args["n"] ** 2)}], "isError": False}
    elif method == "ping":
        result = {}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": identifier,
                          "error": {"code": -32601, "message": "Unsupported fixture method"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": identifier, "result": result}), flush=True)
