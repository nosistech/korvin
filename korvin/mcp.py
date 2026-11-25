"""Talk to one local tool server with the Model Context Protocol (MCP), over its standard input and output.

Korvin starts the server without a shell, and sends one JSON-RPC message per line. It tries the new protocol
(2026-07-28) first, and the older "initialize" handshake after any other error or a timeout. Korvin uses only
tools/list and tools/call. It waits a limited time for each answer, and it ignores the server's error output.
"""

import json
import queue
import subprocess
import sys
import threading
import time

from korvin import __version__

MODERN = "2026-07-28"  # the newest protocol version: every request carries the version in "_meta"
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # the versions with a handshake, newest first
CLIENT = {"name": "korvin", "version": __version__}
UNSUPPORTED_VERSION = -32022  # the error code of a new server that does not speak the requested version
NOT_SUPPORTED = -32601  # "method not found": Korvin's answer to each request that an older server sends
PROBE_TIMEOUT = 5.0  # seconds for the first request, which finds out the protocol
START_TIMEOUT = 10.0  # seconds for the handshake, and for the tool list
CALL_TIMEOUT = 60.0  # seconds for one tool call
CLOSE_WAIT = 2.0  # seconds that a server gets to stop, before Korvin ends it
LINE_LIMIT = 1_000_000  # the most bytes in one message line
POLL = 0.1  # while Korvin waits, it checks for Ctrl+C this often, in seconds
TOO_LONG = b"too long"  # what the reader passes on instead of a line that is too long
UNREADABLE = "The tool server sent an answer that Korvin cannot read."
# The server runs in its own process group, so Ctrl+C in the terminal reaches only Korvin. Korvin then stops it.
OWN_GROUP = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
             else {"start_new_session": True})


class ServerError(Exception):
    """The tool server failed, did not answer in time, or sent something that Korvin cannot use."""

    def __init__(self, message: str, code: object = None, supported: object = None) -> None:
        super().__init__(message)
        self.code = code  # the JSON-RPC error code, if the server sent one
        self.supported = supported if isinstance(supported, list) else []  # versions in a version error


class Server:
    """One running tool server. Call start() first, then tools() and call(). Always call close() at the end."""

    def __init__(self, command: list[str], env: dict[str, str]) -> None:
        self.command, self.env = command, env
        self.process: subprocess.Popen | None = None
        self.lines: queue.Queue = queue.Queue()
        self.era = ""  # "modern" or "legacy", once Korvin knows
        self.version = MODERN  # the protocol version in use
        self.last_id = 0

    def start(self) -> None:
        """Start the server and find out which protocol it speaks."""
        self.spawn()
        try:
            found = self.request("server/discover", {}, PROBE_TIMEOUT)
        except ServerError as error:
            if error.code == UNSUPPORTED_VERSION and not set(error.supported) & set(LEGACY):
                raise ServerError(f"The server speaks only the versions {error.supported}. Korvin cannot.") from None
            found = {}
        if (versions := found.get("supportedVersions")) is not None:  # only a new server answers this way
            if not isinstance(versions, list) or MODERN not in versions:
                raise ServerError(f"The server speaks only protocol versions {str(versions)[:80]}. Korvin cannot.")
            self.era = "modern"
            return
        self.spawn()  # start again: some older servers stop, or get confused, after a request that they do not know
        self.era = "legacy"  # an older server: "initialize", then the "initialized" notification
        params = {"protocolVersion": LEGACY[0], "capabilities": {}, "clientInfo": CLIENT}
        self.version = self.request("initialize", params, START_TIMEOUT).get("protocolVersion")
        if self.version not in LEGACY:
            raise ServerError(f"The server wants protocol version {str(self.version)[:20]}. Korvin cannot.")
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def spawn(self) -> None:
        """Start the server process, with a new reader for its output."""
        self.close()
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, env=self.env, **OWN_GROUP)
        except (OSError, ValueError) as error:
            reason = getattr(error, "strerror", None) or error
            raise ServerError(f"Korvin could not start the server: {reason}.") from None
        self.lines = queue.Queue()
        threading.Thread(target=read_lines, args=(self.process.stdout, self.lines), daemon=True).start()

    def tools(self) -> list[dict]:
        """Return the tools that the server lists. Korvin reads only the first page, as the model sees few tools."""
        found = self.request("tools/list", {}, START_TIMEOUT).get("tools")
        if not isinstance(found, list):
            raise ServerError(UNREADABLE)
        return [tool for tool in found if isinstance(tool, dict)]

    def call(self, name: str, arguments: dict, timeout: float = CALL_TIMEOUT) -> tuple[str, bool]:
        """Call one tool. Return the text of its result, and True if the server says that the tool failed."""
        result = self.request("tools/call", {"name": name, "arguments": arguments}, timeout)
        return result_text(result), result.get("isError") is True

    def request(self, method: str, params: dict, timeout: float) -> dict:
        """Send one request and return its result. Raise ServerError for an error, a timeout, or a stopped server."""
        self.last_id += 1
        number = self.last_id
        if self.era != "legacy":
            params = {**params, "_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN, "io.modelcontextprotocol/clientInfo": CLIENT,
                "io.modelcontextprotocol/clientCapabilities": {},
            }}
        self.send({"jsonrpc": "2.0", "id": number, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while (message := self.receive(deadline, number, timeout)).get("id") != number or "method" in message:
            self.refuse(message)
        if "error" in message:
            error = message["error"] if isinstance(message["error"], dict) else {}
            data = error.get("data") if isinstance(error.get("data"), dict) else {}
            text = str(error.get("message"))[:200]
            raise ServerError(f"The server reported an error: {text}", error.get("code"), data.get("supported"))
        result = message.get("result")
        if not isinstance(result, dict):
            raise ServerError(UNREADABLE)
        if result.get("resultType", "complete") != "complete":
            raise ServerError("The server sent a kind of result that Korvin does not support, such as a question.")
        return result

    def receive(self, deadline: float, number: int, timeout: float) -> dict:
        """Return the next message from the server. Skip lines that are not JSON objects."""
        while True:
            try:
                raw = self.lines.get(timeout=POLL)
            except queue.Empty:
                if time.monotonic() < deadline:
                    continue
                if self.era:  # an older server must not get a notification before its handshake
                    params = {"requestId": number, "reason": "Korvin stopped waiting."}
                    self.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": params})
                raise ServerError(f"The server did not answer within {timeout:g} seconds.") from None
            if raw is None:
                self.lines.put(None)  # so that the next request also sees the end at once
                raise ServerError("The server stopped.")
            if raw is TOO_LONG:
                raise ServerError(f"The server sent a message longer than {LINE_LIMIT:,} bytes.")
            try:
                message = json.loads(raw.decode("utf-8"))
            except (ValueError, RecursionError):
                continue  # not a message, so Korvin skips it
            if isinstance(message, dict):
                return message

    def refuse(self, message: dict) -> None:
        """Answer a request from an older server: "ping" gets an empty result, any other request a refusal."""
        # The new protocol lets no server send requests, so Korvin ignores them there. It ignores all notifications.
        if self.era == "legacy" and "method" in message and isinstance(message.get("id"), (str, int)):
            reply = {"result": {}} if message["method"] == "ping" else {
                "error": {"code": NOT_SUPPORTED, "message": "Korvin does not support this request."}}
            self.send({"jsonrpc": "2.0", "id": message["id"], **reply})

    def send(self, message: dict) -> None:
        """Write one message as one line. The JSON text is ASCII, so it never holds a raw line break."""
        try:
            self.process.stdin.write(json.dumps(message).encode("ascii") + b"\n")
            self.process.stdin.flush()
        except (OSError, ValueError):
            raise ServerError("The server stopped.") from None

    def close(self) -> None:
        """Stop the server: close its input, wait, then end the process. A second call does nothing."""
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.stdin.close()
            process.wait(CLOSE_WAIT)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()  # on Windows, this is TerminateProcess
            process.wait()


def read_lines(stream, lines: queue.Queue) -> None:
    """Pass each line from the server to the queue, and None at the end. A line that is too long becomes TOO_LONG."""
    skipping = False
    try:
        while raw := stream.readline(LINE_LIMIT + 1):
            if not skipping:
                lines.put(raw if len(raw) <= LINE_LIMIT else TOO_LONG)
            skipping = not raw.endswith(b"\n")
    except (OSError, ValueError):
        pass
    finally:
        stream.close()
        lines.put(None)


def result_text(result: dict) -> str:
    """Return the text items of a tool result. Name each other item, such as an image, but leave out its data."""
    parts, items = [], result.get("content")
    for item in items if isinstance(items, list) else []:
        kind = item.get("type") if isinstance(item, dict) else None
        text = item.get("text") if kind == "text" else None
        parts.append(text if isinstance(text, str) else f"[Korvin left out an item of type {str(kind)[:20]}.]")
    if not parts and "structuredContent" in result:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    return "\n".join(parts)
