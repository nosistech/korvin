"""A small tool server for the tests. It speaks only the new protocol, 2026-07-28, with no handshake.

Every request must carry the protocol version and the client capabilities in "_meta". Without them, it refuses.
It refuses "initialize", as a server of the new protocol does.
The first argument is a mode: "normal", or "future", which supports only a version that Korvin does not know.
With a file path as its second argument, it writes each message that it receives into that file, one per line.
"""

import json
import sys

VERSION = "2026-07-28"
META = "io.modelcontextprotocol/"
TOOLS = [
    {"name": "echo", "description": "Repeat the text.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "fail", "description": "Always fail.", "inputSchema": {"type": "object", "additionalProperties": False}},
    {"name": "picture", "description": "Return a picture and a caption.", "inputSchema": {"type": "object"}},
]


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def result(method: str, params: dict) -> dict:
    """Return the result of one request, or raise LookupError for an unknown method or tool."""
    if method == "server/discover":
        return {"supportedVersions": [VERSION], "capabilities": {"tools": {}},
                "_meta": {META + "serverInfo": {"name": "modern-test", "version": "1.0"}}}
    if method == "tools/list":
        return {"tools": TOOLS}
    name = params.get("name")
    if method == "tools/call" and name == "echo":
        return {"content": [{"type": "text", "text": str(params.get("arguments", {}).get("text"))}]}
    if method == "tools/call" and name == "fail":
        return {"content": [{"type": "text", "text": "The tool broke on purpose."}], "isError": True}
    if method == "tools/call" and name == "picture":
        return {"content": [{"type": "image", "data": "AAAA", "mimeType": "image/png"}, {"type": "text", "text": "A cat."}]}
    raise LookupError(method)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    record = open(sys.argv[2], "a", encoding="utf-8") if len(sys.argv) > 2 else None
    for line in sys.stdin:
        if record:
            record.write(line)
            record.flush()
        message = json.loads(line)
        if "id" not in message:
            continue  # a notification
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        meta = (message.get("params") or {}).get("_meta") or {}
        if META + "protocolVersion" not in meta or META + "clientCapabilities" not in meta:
            reply["error"] = {"code": -32602, "message": "Invalid params: the request has no _meta fields"}
        elif mode == "future" or meta[META + "protocolVersion"] != VERSION:
            reply["error"] = {"code": -32022, "message": "Unsupported protocol version",
                              "data": {"supported": ["2027-01-01"], "requested": meta[META + "protocolVersion"]}}
        else:
            try:
                reply["result"] = {"resultType": "complete", **result(message["method"], message.get("params") or {})}
            except LookupError:
                reply["error"] = {"code": -32601, "message": f"Unknown method {message['method']}"}
        send(reply)


if __name__ == "__main__":
    main()
