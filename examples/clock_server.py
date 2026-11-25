"""An example tool server for Korvin: a clock and a unit converter. It needs no network and no extra package.

It speaks the Model Context Protocol (MCP) over its standard input and output, with one JSON message per line.
It understands both kinds of client: the new protocol (2026-07-28), and the older one with an "initialize" handshake.
It writes nothing except protocol messages to its output.

To add it to Korvin, type this in the Korvin folder, with the full path of this file:
    python -m korvin server add clock --risk read -- python C:\\path\\to\\Korvin\\examples\\clock_server.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone

NEW_VERSION = "2026-07-28"
OLD_VERSION = "2025-11-25"
SERVER_INFO = {"name": "korvin-example-clock", "version": "1.0"}

# Each conversion: (from, to) -> the function that converts a value.
CONVERSIONS = {
    ("km", "mi"): lambda value: value / 1.609344,
    ("mi", "km"): lambda value: value * 1.609344,
    ("kg", "lb"): lambda value: value / 0.45359237,
    ("lb", "kg"): lambda value: value * 0.45359237,
    ("c", "f"): lambda value: value * 9 / 5 + 32,
    ("f", "c"): lambda value: (value - 32) * 5 / 9,
}
UNITS = sorted({unit for pair in CONVERSIONS for unit in pair})

TOOLS = [
    {
        "name": "now",
        "description": "Tell the current date and time. Give the offset from UTC in hours, such as 1 or -5.",
        "inputSchema": {
            "type": "object",
            "properties": {"utc_offset": {"type": "number", "description": "Hours from UTC, from -12 to 14. Default 0."}},
            "additionalProperties": False,
        },
    },
    {
        "name": "convert",
        "description": "Convert a value between km and mi, kg and lb, or degrees c and f.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "from_unit": {"type": "string", "enum": UNITS},
                "to_unit": {"type": "string", "enum": UNITS},
            },
            "required": ["value", "from_unit", "to_unit"],
            "additionalProperties": False,
        },
    },
]


def now(arguments: dict) -> str:
    """Return the current date and time at an offset from UTC."""
    offset = arguments.get("utc_offset", 0)
    if not isinstance(offset, (int, float)) or not -12 <= offset <= 14:
        raise ValueError("utc_offset must be a number from -12 to 14.")
    moment = datetime.now(timezone(timedelta(hours=offset)))
    return moment.strftime("%A %d %B %Y, %H:%M") + f" (UTC{offset:+g})"


def convert(arguments: dict) -> str:
    """Return a value converted from one unit to another."""
    value, pair = arguments.get("value"), (arguments.get("from_unit"), arguments.get("to_unit"))
    if not isinstance(value, (int, float)) or pair not in CONVERSIONS:
        pairs = ", ".join(f"{a} to {b}" for a, b in CONVERSIONS)
        raise ValueError(f"Give a number and two units. The conversions are: {pairs}.")
    return f"{value:g} {pair[0]} = {CONVERSIONS[pair](value):.2f} {pair[1]}"


def call_tool(params: dict) -> dict:
    """Run one tool. A wrong input becomes a tool error, so the model can read it and try again."""
    tools = {"now": now, "convert": convert}
    name, arguments = params.get("name"), params.get("arguments") or {}
    if name not in tools:
        raise LookupError(f"Unknown tool: {name}")
    try:
        return {"content": [{"type": "text", "text": tools[name](arguments)}], "isError": False}
    except ValueError as error:
        return {"content": [{"type": "text", "text": str(error)}], "isError": True}


def result_of(method: str, params: dict) -> dict:
    """Return the result of one request. Raise LookupError for a tool, or KeyError for a method, that it does not have."""
    if method == "server/discover":  # the new protocol: an optional first question about the server
        return {"supportedVersions": [NEW_VERSION, OLD_VERSION], "capabilities": {"tools": {}},
                "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO}}
    if method == "initialize":  # the older protocol: the handshake
        return {"protocolVersion": OLD_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params)
    raise KeyError(method)


def reply_to(message: dict) -> dict | None:
    """Return the reply to one message, or None for a notification, which gets no reply."""
    if "id" not in message:
        return None
    params = message.get("params") or {}
    version = (params.get("_meta") or {}).get("io.modelcontextprotocol/protocolVersion")
    if version is not None and version != NEW_VERSION:
        error = {"code": -32022, "message": "Unsupported protocol version",
                 "data": {"supported": [NEW_VERSION, OLD_VERSION], "requested": version}}
        return {"jsonrpc": "2.0", "id": message["id"], "error": error}
    try:
        result = {"resultType": "complete", **result_of(message.get("method"), params)}
    except KeyError:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method not found"}}
    except LookupError as problem:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": str(problem)}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def main() -> None:
    """Answer each message until the client closes the input."""
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = reply_to(message) if isinstance(message, dict) else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
