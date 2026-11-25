"""An example tool server for Korvin: web search and web page reading, through Ollama's hosted web search API.

It offers two tools. "search" sends a query to https://ollama.com/api/web_search.
"fetch" sends one web address to https://ollama.com/api/web_fetch, and returns the page as cut plain text.
So every query and every address leaves this computer and goes to Ollama's service.

It speaks the Model Context Protocol (MCP) over its standard input and output, with one JSON message per line.
It understands both kinds of client: the new protocol (2026-07-28), and the older one with an "initialize" handshake.
It needs no extra package. It writes nothing except protocol messages to its output.

Safety rules inside this server:
- It talks only to ollama.com, over HTTPS, with the normal certificate checks. It never follows a redirect.
- It reads the key only from the environment variable OLLAMA_API_KEY. It never prints or returns the key.
- Each request has a time limit, and the server reads at most RESPONSE_LIMIT bytes of each reply.
- It cuts each search result and each page, so that a small model gets short, plain text.

To add it to Korvin, get a key at https://ollama.com/settings/keys, store it in the environment variable
OLLAMA_API_KEY, and type this in the Korvin folder, with the full path of this file:
    python -m korvin server add web --risk read --env OLLAMA_API_KEY -- python C:\\path\\to\\search_server.py
"""

import http.client
import json
import os
import re
import ssl
import sys
import time
from urllib.parse import urlsplit

NEW_VERSION = "2026-07-28"
OLD_VERSION = "2025-11-25"
SERVER_INFO = {"name": "korvin-example-search", "version": "1.0"}
API_HOST = "ollama.com"  # the only host that this server talks to
KEY_VARIABLE = "OLLAMA_API_KEY"
# For the unit tests only: an address of a fake API on this computer, such as http://127.0.0.1:8123.
# The server refuses any other value, so the variable cannot send the key to another computer.
TEST_VARIABLE = "KORVIN_SEARCH_TEST_URL"
TEST_URL = r"http://127\.0\.0\.1:(\d{1,5})"
TIME_LIMIT = 20.0  # seconds for one request to the API. Korvin itself waits 60 seconds for a tool call.
RESPONSE_LIMIT = 2_000_000  # the most bytes that the server reads of one reply
QUERY_LIMIT = 300  # the longest search query, in characters
ADDRESS_LIMIT = 2_000  # the longest web address, in characters
MAX_RESULTS = 5  # the most search results for one query. Ollama allows up to 10.
SNIPPET_LIMIT = 500  # the most characters of each search result's text
PAGE_LIMIT = 8_000  # the most characters of a fetched page
ERROR_LIMIT = 200  # the most characters of an error message from the API
NO_KEY = (f"The search server has no key. Store your Ollama API key in the environment variable {KEY_VARIABLE}, "
          f"and add the server with --env {KEY_VARIABLE}.")

TOOLS = [
    {
        "name": "search",
        "description": "Search the web with Ollama's web search service. Returns the title, address, and a short text "
                       "of each result. The query leaves this computer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The words to search for."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS,
                                "description": f"How many results, from 1 to {MAX_RESULTS}. Default 3."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch",
        "description": f"Read one web page with Ollama's web fetch service. Returns its title and its text, cut to "
                       f"{PAGE_LIMIT:,} characters. The address leaves this computer.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The full address, starting with https://"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
]


class ToolFailure(Exception):
    """A tool could not do its work. The message is plain text for the model and the user."""


def cut(text: object, limit: int) -> str:
    """Return the text, cut to the limit, with a note when it was cut."""
    text = text if isinstance(text, str) else ""
    return text if len(text) <= limit else text[:limit] + f" [cut to {limit:,} characters]"


def api_connection() -> http.client.HTTPConnection:
    """Return an unopened connection to the one API host. Only the tests may point it to a fake on this computer."""
    test_url = os.environ.get(TEST_VARIABLE)
    if not test_url:
        return http.client.HTTPSConnection(API_HOST, 443, timeout=TIME_LIMIT, context=ssl.create_default_context())
    found = re.fullmatch(TEST_URL, test_url)
    if not found:
        raise ToolFailure(f"{TEST_VARIABLE} may only name a fake on this computer, such as http://127.0.0.1:8123.")
    return http.client.HTTPConnection("127.0.0.1", int(found.group(1)), timeout=TIME_LIMIT)


def read_reply(response: http.client.HTTPResponse, deadline: float) -> bytes:
    """Read the body of a reply. Stop at RESPONSE_LIMIT bytes, or when the time limit has passed."""
    data = b""
    while chunk := response.read(65_536):
        data += chunk
        if len(data) > RESPONSE_LIMIT:
            raise ToolFailure(f"Ollama sent more than {RESPONSE_LIMIT:,} bytes, so the server stopped reading.")
        if time.monotonic() > deadline:
            raise TimeoutError
    return data


def post(path: str, payload: dict) -> dict:
    """Send one request to the API, and return its JSON reply. Raise ToolFailure with a plain reason."""
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise ToolFailure(NO_KEY)
    if not re.fullmatch(r"[\x21-\x7e]+", key):
        raise ToolFailure(f"The key in {KEY_VARIABLE} has spaces or other characters that a key cannot have.")
    connection = api_connection()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    deadline = time.monotonic() + TIME_LIMIT
    try:
        connection.request("POST", path, body=json.dumps(payload).encode("utf-8"), headers=headers)
        response = connection.getresponse()
        data = read_reply(response, deadline)
    except TimeoutError:
        raise ToolFailure(f"Ollama did not answer within {TIME_LIMIT:g} seconds. Try again later.") from None
    except (OSError, http.client.HTTPException) as error:
        reason = getattr(error, "strerror", None) or str(error) or type(error).__name__
        raise ToolFailure(f"The search server could not reach {API_HOST}: {cut(reason, ERROR_LIMIT)}") from None
    finally:
        connection.close()
    if response.status != 200:
        raise ToolFailure(status_text(response.status, data).replace(key, "[key]"))
    try:
        reply = json.loads(data)
    except ValueError:
        reply = None
    if not isinstance(reply, dict):
        raise ToolFailure("Ollama sent a reply that the search server cannot read.")
    return reply


def status_text(status: int, data: bytes) -> str:
    """Return a plain explanation of an error reply from the API."""
    if 300 <= status < 400:
        return f"Ollama answered with a redirect (error {status}). The search server never follows a redirect."
    if status in (401, 403):
        return f"Ollama refused the key (error {status}). Check the key in {KEY_VARIABLE}."
    if status == 429:
        return "Ollama says that there were too many requests (error 429). Wait a minute, then try again."
    try:
        message = json.loads(data).get("error")
    except (ValueError, AttributeError):
        message = None
    details = cut(message, ERROR_LIMIT) if isinstance(message, str) else "no details"
    return f"Ollama returned error {status}: {details}"


def search(arguments: dict) -> str:
    """Search the web, and return the results as numbered plain text."""
    query, count = arguments.get("query"), arguments.get("max_results", 3)
    if not isinstance(query, str) or not query.strip() or len(query) > QUERY_LIMIT:
        raise ToolFailure(f"Give a query of 1 to {QUERY_LIMIT} characters.")
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_RESULTS:
        raise ToolFailure(f"Give max_results as a whole number from 1 to {MAX_RESULTS}.")
    results = post("/api/web_search", {"query": query.strip(), "max_results": count}).get("results")
    found = [item for item in results if isinstance(item, dict)][:count] if isinstance(results, list) else []
    if not found:
        return f"No results for: {query.strip()}"
    lines = []
    for number, item in enumerate(found, 1):
        lines += [f"{number}. {cut(item.get('title'), 200)}", f"   {cut(item.get('url'), ADDRESS_LIMIT)}",
                  f"   {cut(item.get('content'), SNIPPET_LIMIT)}"]
    return "\n".join(lines)


def fetch(arguments: dict) -> str:
    """Read one web page, and return its title and its text, cut to PAGE_LIMIT characters."""
    url = arguments.get("url")
    try:
        parts = urlsplit(url) if isinstance(url, str) and len(url) <= ADDRESS_LIMIT else None
        good = parts is not None and parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:  # for example, a broken IPv6 address
        good = False
    if not good or re.search(r"\s", url):
        raise ToolFailure("Give one full web address that starts with https:// or http://.")
    page = post("/api/web_fetch", {"url": url})
    return f"Title: {cut(page.get('title'), 200)}\nAddress: {url}\n\n{cut(page.get('content'), PAGE_LIMIT)}"


def call_tool(params: dict) -> dict:
    """Run one tool. A failure becomes a tool error, so the model can read it and try again."""
    tools = {"search": search, "fetch": fetch}
    name, arguments = params.get("name"), params.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    if name not in tools:
        raise LookupError(f"Unknown tool: {name}")
    try:
        return {"content": [{"type": "text", "text": tools[name](arguments)}], "isError": False}
    except ToolFailure as failure:
        return {"content": [{"type": "text", "text": str(failure)}], "isError": True}


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
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    version = meta.get("io.modelcontextprotocol/protocolVersion")
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
