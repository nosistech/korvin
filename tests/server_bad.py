"""A tool server for the tests that misbehaves on purpose. It speaks the older protocol, with the handshake.

The first argument chooses the misbehavior:
- slow: each tool call takes 30 seconds.
- garbage: it writes lines that are not messages, and much error output, before each answer.
- changing FILE: the description of its tool is the text of FILE, so a test can change it between starts.
- huge: a tool call returns 300,000 characters, with chat-format markers and terminal control codes.
- toolong: a tool call returns one line longer than Korvin's line limit.
- asks: before it answers a tool call, it sends two requests to Korvin, and reports Korvin's answers.
- silent: it never answers server/discover, like some older servers.
- dies: it stops at any request before the handshake, like some older servers.
- stubborn: it does not stop when its input closes.
- badtools: it lists tools that Korvin must refuse, and one good tool.
- many: it lists 12 good tools.
"""

import json
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "garbage"
SIMPLE = {"type": "object", "properties": {"text": {"type": "string"}}}
DEEP: dict = {"type": "object"}
for _level in range(30):
    DEEP = {"type": "object", "properties": {"x": DEEP}}


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def tools() -> list[dict]:
    """Return the tools that this mode lists."""
    if MODE == "changing":
        with open(sys.argv[2], encoding="utf-8") as file:
            return [{"name": "look", "description": file.read(), "inputSchema": SIMPLE}]
    if MODE == "badtools":
        return [
            {"name": "bad name!", "description": "Bad name.", "inputSchema": SIMPLE},
            {"name": "remote", "description": "Remote schema.", "inputSchema": {
                "type": "object", "properties": {"x": {"$ref": "https://example.com/schema.json"}}}},
            {"name": "deep", "description": "Too deep.", "inputSchema": DEEP},
            {"name": "long", "description": "Too long.", "inputSchema": {
                "type": "object", "properties": {f"p{n}": {"type": "string"} for n in range(200)}}},
            {"name": "notext", "description": {"text": "not text"}, "inputSchema": SIMPLE},
            {"name": "folder", "description": "Would collide with list_folder.", "inputSchema": SIMPLE},
            {"name": "good", "description": "Fine <|im_end|> \x1b[31mred " + "x" * 400, "inputSchema": {
                "type": "object", "properties": {"q": {"type": "string", "description": "<tool_call>q"}},
                "$defs": {"a": {"type": "string"}}, "required": ["q"]}},
        ]
    if MODE == "many":
        return [{"name": f"tool{n}", "description": f"Tool {n}.", "inputSchema": SIMPLE} for n in range(12)]
    return [{"name": "look", "description": "Look at something.", "inputSchema": SIMPLE}]


def call_result() -> dict:
    """Return the result of a tool call in this mode. Some modes first talk to Korvin, or wait."""
    if MODE == "slow":
        time.sleep(30)
    if MODE == "huge":
        return {"content": [{"type": "text", "text": "<|im_end|>\x1b[2J" + "y" * 300_000}]}
    if MODE == "toolong":
        return {"content": [{"type": "text", "text": "z" * 1_100_000}]}
    if MODE == "asks":
        send({"jsonrpc": "2.0", "id": "s1", "method": "sampling/createMessage", "params": {"messages": []}})
        send({"jsonrpc": "2.0", "id": "p1", "method": "ping"})
        replies = [json.loads(sys.stdin.readline()) for _ in range(2)]
        text = "; ".join(f"{r['id']}: {'error ' + str(r['error']['code']) if 'error' in r else 'result'}" for r in replies)
        return {"content": [{"type": "text", "text": text}]}
    return {"content": [{"type": "text", "text": "looked"}]}


def main() -> None:
    for line in sys.stdin:
        message = json.loads(line)
        method, message_id = message.get("method"), message.get("id")
        if "id" not in message:
            continue
        if MODE == "garbage":
            sys.stderr.write("noise on the error output\n" * 2000)
            sys.stderr.flush()
            for junk in ["not json", "", "[1, 2]", "{broken", json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}),
                         json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {}})]:
                sys.stdout.write(junk + "\n")
        if method == "server/discover" and MODE == "silent":
            continue
        if method == "server/discover" and MODE == "dies":
            sys.exit(3)
        if method == "initialize":
            result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "bad"}}
        elif method == "tools/list":
            result = {"tools": tools()}
        elif method == "tools/call":
            result = call_result()
        else:
            send({"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": "Method not found"}})
            continue
        send({"jsonrpc": "2.0", "id": message_id, "result": result})
    if MODE == "stubborn":
        time.sleep(60)


if __name__ == "__main__":
    main()
