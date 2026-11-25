"""A small tool server for the tests. It speaks the older protocol, with the "initialize" handshake.

Like many older servers, it refuses every request before the handshake.
It writes a line to its error output at the start, which Korvin must not treat as an error.
With a file path as its first argument, it writes each message that it receives into that file, one per line.
"""

import json
import sys

TOOLS = [
    {"name": "echo", "description": "Repeat the text.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "add", "description": "Add two numbers.",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}}},
]


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def answer(message_id: object, method: str, params: dict) -> dict:
    """Return the result of one request, or raise LookupError for an unknown method."""
    if method == "initialize":
        return {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "legacy-test"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call" and params.get("name") == "echo":
        return {"content": [{"type": "text", "text": str(params.get("arguments", {}).get("text"))}], "isError": False}
    if method == "tools/call" and params.get("name") == "add":
        arguments = params.get("arguments", {})
        return {"content": [{"type": "text", "text": str(arguments.get("a", 0) + arguments.get("b", 0))}]}
    raise LookupError(method)


def main() -> None:
    record = open(sys.argv[1], "a", encoding="utf-8") if len(sys.argv) > 1 else None
    print("legacy test server: started", file=sys.stderr, flush=True)
    ready = False
    for line in sys.stdin:
        if record:
            record.write(line)
            record.flush()
        message = json.loads(line)
        method, message_id = message.get("method"), message.get("id")
        if "id" not in message:
            ready = ready or method == "notifications/initialized"
            continue
        if not ready and method != "initialize":
            send({"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": f"Unknown method {method}"}})
            continue
        try:
            send({"jsonrpc": "2.0", "id": message_id, "result": answer(message_id, method, message.get("params") or {})})
        except LookupError:
            send({"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": f"Unknown method {method}"}})


if __name__ == "__main__":
    main()
