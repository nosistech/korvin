"""A tiny fake model service for the tests.

It speaks just enough of the OpenAI-style API that Ollama serves.
It listens on 127.0.0.1 only and records every chat request body it receives.
A script can make it ask for tools, one reply for each request, before its normal answer.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NO_TOOLS_MESSAGE = "registry.ollama.ai/library/fake-model:latest does not support tools"


class FakeModel:
    """A fake model service. Use it as a context manager: with FakeModel() as fake: ..."""

    def __init__(
        self,
        pieces: tuple[str, ...] = ("Hello", " there"),
        models: tuple[str, ...] | None = ("fake-model",),
        failures: int = 0,
        fail_status: int = 500,
        raw_stream: bytes | None = None,
        thinking: tuple[str, ...] = (),
        start_delay: float = 0.0,
        line_delay: float = 0.0,
        script: list[list[dict] | bytes] | None = None,
        refuse_tools: bool = False,
        context: int | None = 65_536,
        usage: bool = False,
        gpu: float | None = None,
        shows: dict[str, dict] | None = None,
        create_status: int = 200,
    ) -> None:
        self.gpu = gpu  # the share of the loaded model on the graphics card that /api/ps reports, or None for no sizes
        self.shows = shows or {}  # the /api/show reply for each model name; others get a 404
        self.create_status = create_status  # the status of the reply to /api/create
        self.pieces = list(pieces)
        self.models = models  # None sends "data": null, as Ollama does with no models
        self.failures = failures  # how many chat requests fail before the normal answers
        self.fail_status = fail_status
        self.raw_stream = raw_stream  # bytes to send instead of the normal stream
        self.thinking = list(thinking)  # thinking pieces to send before the answer, as a reasoning model does
        self.start_delay = start_delay  # seconds to wait before the reply begins, like a model that loads
        self.line_delay = line_delay  # seconds to wait before each line of the stream
        # One reply for each chat request, in order: a list of deltas, or raw bytes. Then the normal answer.
        self.script = list(script or [])
        self.refuse_tools = refuse_tools  # answer 400 "does not support tools" to a request with tools, as Ollama does
        self.context = context  # the context size that /api/ps reports, or None to report no loaded model
        # Send the token count at the end of each stream. The fake counts one token for each character of JSON.
        self.usage = usage
        self.requests: list[dict] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.fake = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def __enter__(self) -> "FakeModel":
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()


def tool_call(name: str, arguments: str, index: int = 0, call_id: str | None = None, pieces: int = 1) -> list[dict]:
    """Return the deltas of one streamed tool call. With pieces > 1, the name and the arguments arrive in pieces."""
    deltas = []
    names, texts = split(name, pieces), split(arguments, pieces)
    for number in range(pieces):
        part = {"index": index, "function": {"name": names[number], "arguments": texts[number]}}
        if number == 0:
            part["type"] = "function"
            if call_id is not None:
                part["id"] = call_id
        deltas.append({"content": "", "tool_calls": [part]})
    return deltas


def split(text: str, pieces: int) -> list[str]:
    """Cut text into the given number of pieces. Some pieces can be empty."""
    size = -(-len(text) // pieces) or 1
    return [text[number * size : (number + 1) * size] for number in range(pieces)]


def answer(text: str) -> list[dict]:
    """Return the deltas of a plain answer."""
    return [{"content": text}]


def thinking(*texts: str) -> list[dict]:
    """Return the deltas of thinking only, as Ollama sends them. Add answer() after it for a reply with text."""
    return [{"content": "", "reasoning": text} for text in texts]


def stream_body(pieces: list[str], thinking: list[str], tokens: int | None = None) -> bytes:
    """Build a server-sent-event stream in the same shape that Ollama sends."""
    deltas = [{"role": "assistant", "content": ""}]
    # Ollama sends the thinking in "reasoning", with an empty "content".
    deltas += [{"content": "", "reasoning": text} for text in thinking]
    deltas += [{"content": piece} for piece in pieces]
    deltas.append({"content": ""})
    return events_body(deltas, tokens)


def events_body(deltas: list[dict], tokens: int | None = None) -> bytes:
    """Build a stream that sends each delta as one event, then the token count if given, then the end."""
    lines = []
    for delta in deltas:
        event = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta}]}
        lines.append("data: " + json.dumps(event, ensure_ascii=False) + "\n\n")
    if tokens is not None:
        # Ollama sends the counts in one last event with no choices.
        lines.append("data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": tokens}}) + "\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass  # keep the test output clean

    def do_GET(self) -> None:
        fake = self.server.fake
        if self.path == "/api/ps":
            loaded = [{"name": "fake-model:latest", "context_length": fake.context}] if fake.context else []
            if loaded and fake.gpu is not None:
                loaded[0].update(size=2_000_000_000, size_vram=int(2_000_000_000 * fake.gpu))
            self._send(200, {"models": loaded})
            return
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": name, "size": 1_945_323_638} for name in fake.models or ()]})
            return
        if self.path != "/v1/models":
            self._send(404, {"error": {"message": "not found"}})
            return
        data = None
        if fake.models is not None:
            data = [{"id": name, "object": "model"} for name in fake.models]
        self._send(200, {"object": "list", "data": data})

    def do_POST(self) -> None:
        fake = self.server.fake
        length = int(self.headers["Content-Length"])
        fake.requests.append(json.loads(self.rfile.read(length)))
        tokens = len(json.dumps(fake.requests[-1].get("messages"))) if fake.usage else None
        time.sleep(fake.start_delay)
        name = fake.requests[-1].get("model")
        if self.path == "/api/show":
            self._send(200, fake.shows[name]) if name in fake.shows else self._send(404, {"error": "not found"})
        elif self.path == "/api/create":
            self._send(fake.create_status, {"status": "success"} if fake.create_status == 200 else {"error": "no room"})
        elif self.path != "/v1/chat/completions":
            self._send(404, {"error": {"message": "not found"}})
        elif fake.failures > 0:
            fake.failures -= 1
            self._send(fake.fail_status, {"error": {"message": "fake failure"}})
        elif fake.refuse_tools and "tools" in fake.requests[-1]:
            self._send(400, {"error": {"message": NO_TOOLS_MESSAGE, "type": "api_error"}})
        elif fake.script:
            reply = fake.script.pop(0)
            self._send_bytes(200, reply if isinstance(reply, bytes) else events_body(reply, tokens), "text/event-stream")
        else:
            body = fake.raw_stream if fake.raw_stream is not None else stream_body(fake.pieces, fake.thinking, tokens)
            self._send_bytes(200, body, "text/event-stream", fake.line_delay)

    def _send(self, status: int, data: dict) -> None:
        self._send_bytes(status, json.dumps(data).encode("utf-8"), "application/json")

    def _send_bytes(self, status: int, body: bytes, content_type: str, line_delay: float = 0.0) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if 300 <= status < 400:
                self.send_header("Location", "http://192.0.2.1/v1/chat/completions")
            self.end_headers()
            for line in body.splitlines(keepends=True) if line_delay else [body]:
                time.sleep(line_delay)
                self.wfile.write(line)
        except ConnectionError:
            pass  # the client left early, which some tests do on purpose
