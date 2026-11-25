"""Talk to the model service. This is the only Korvin file that uses the network.

Korvin speaks the OpenAI-style chat API that Ollama serves.
For the setup and the checks, it also uses Ollama's own API to list, describe, and copy models.
Each request goes to this computer only. Korvin never follows a redirect.
"""

import json
from collections.abc import Generator
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPResponse

from korvin import guard
from korvin.config import ConfigError, Provider, parse_base_url

UNREADABLE = "The model service sent a reply that Korvin cannot read."
ERROR_READ_LIMIT = 2000
ERROR_SHOW_LIMIT = 200
LINE_LIMIT = 1_000_000  # the most bytes that one stream line can have, with its line ending
SAMPLING = {"temperature": 0.6, "presence_penalty": 0.0}  # sent with each chat request, in place of the stored values (D-023)


class DoorError(Exception):
    """Korvin could not get a usable answer from the model service."""


class ToolsNotSupported(DoorError):
    """The model service says that this model cannot use tools."""


@dataclass(frozen=True)
class Piece:
    """One piece of a streamed reply. The kind is "thinking" or "answer"."""
    kind: str
    text: str


@dataclass(frozen=True)
class ToolCall:
    """One tool call that the model asked for. Nobody has checked the JSON text of its arguments yet."""
    id: str
    name: str
    arguments_text: str


@dataclass(frozen=True)
class Usage:
    """The size of the prompt of one request, in tokens, as the model service counted it."""
    prompt_tokens: int


class ModelDoor:
    """The connection point to one model service."""

    def __init__(self, provider: Provider, timeout: float = 120.0, start_timeout: float = 300.0) -> None:
        self.provider = provider
        self.timeout = timeout  # the longest wait for the next piece of a reply
        # The first reply after the service starts can take minutes, because the model must load.
        self.start_timeout = start_timeout  # the longest wait for a reply to begin

    def list_models(self) -> list[str]:
        """Return the names of the models that the service has installed."""
        return model_names(self._json("/models", native=False))

    def installed_models(self) -> list[dict]:
        """Return Ollama's entry for each installed model. Each entry has at least a "name"."""
        data = self._json("/api/tags")
        models = (data.get("models") if isinstance(data, dict) else None) or []
        named = isinstance(models, list) and all(isinstance(e, dict) and isinstance(e.get("name"), str) for e in models)
        if not named:
            raise DoorError(UNREADABLE)
        return models

    def model_facts(self, model: str) -> dict:
        """Return what Ollama's /api/show says about an installed model, such as its capabilities. It loads nothing."""
        facts = self._json("/api/show", {"model": model})
        if not isinstance(facts, dict):
            raise DoorError(UNREADABLE)
        return facts

    def create_copy(self, name: str, base: str, parameters: dict) -> None:
        """Ask Ollama to create a model from an installed one, with other parameters. The copy shares its files."""
        reply = self._json("/api/create", {"model": name, "from": base, "parameters": parameters, "stream": False})
        if not isinstance(reply, dict) or reply.get("status") != "success":
            raise DoorError(f"Ollama did not create the model {name}.")

    def context_size(self, model: str) -> int | None:
        """Return the context size, in tokens, of the model as Ollama has it loaded now, or None if unknown."""
        size = self._loaded(model).get("context_length")
        return size if is_count(size) and size > 0 else None

    def gpu_share(self, model: str) -> float | None:
        """Return the share of the loaded model that is on the graphics card, from 0.0 to 1.0, or None if unknown."""
        entry = self._loaded(model)
        size, vram = entry.get("size"), entry.get("size_vram")
        return vram / size if is_count(size) and is_count(vram) and size > 0 else None

    def _loaded(self, model: str) -> dict:
        """Return Ollama's entry for the model as it is loaded now, or an empty dict if Korvin cannot find it."""
        try:
            entries = self._json("/api/ps").get("models")
        except (DoorError, AttributeError):
            return {}
        for entry in entries if isinstance(entries, list) else []:
            names = {entry.get("name"), entry.get("model")} if isinstance(entry, dict) else set()
            if names & {model, f"{model}:latest"}:
                return entry
        return {}

    def _json(self, path: str, payload: dict | None = None, native: bool = True) -> object:
        """Send one request, GET without a payload and POST with one, and return the JSON reply.

        Ollama's own API ("native") lives at the same address as the OpenAI-style API, without "/v1".
        """
        connection, base_path = self._connect()
        try:
            base_path = base_path.removesuffix("/v1") if native else base_path
            method = "GET" if payload is None else "POST"
            return parse_json(decode(send(connection, method, base_path + path, payload, self.timeout).read()))
        except (OSError, HTTPException) as error:
            raise self._network_error(error) from None
        finally:
            connection.close()

    def stream_chat(
        self, model: str, messages: list[dict], tools: list[dict] | None = None
    ) -> Generator[Piece | ToolCall | Usage, None, None]:
        """Send the conversation, then yield the thinking and the answer in pieces as they arrive.

        If the model asks for tools, yield one ToolCall for each at the end, in the model's order.
        If the service counts the prompt's tokens, yield one Usage at the very end.
        """
        body = {"model": model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}, **SAMPLING}
        body |= {"tools": tools} if tools else {}
        calls: dict[int, dict] = {}
        usage = None
        connection, base_path = self._connect()
        try:
            response = send(connection, "POST", base_path + "/chat/completions", body, self.timeout)
            for line in stream_lines(response):
                if line == "data: [DONE]":
                    yield from finished_calls(calls)
                    if usage:
                        yield usage
                    return
                if line:
                    delta = delta_from_line(line)
                    if isinstance(delta, Usage):
                        usage = delta
                        continue
                    add_call_parts(calls, delta)
                    yield from pieces_from_delta(delta)
        except (OSError, HTTPException) as error:
            raise self._network_error(error) from None
        finally:
            # Closing the connection also tells the service to stop an answer that Korvin left early.
            connection.close()
        raise DoorError("The model service stopped before the answer was complete.")

    def _connect(self) -> tuple[HTTPConnection, str]:
        # Check the address again before every request, in case a Provider skipped the settings check.
        try:
            host, port, base_path = parse_base_url(self.provider.base_url)
        except ConfigError as error:
            raise DoorError(str(error)) from None
        if self.provider.remote or not guard.is_loopback_host(host):
            raise DoorError(f"Korvin refuses to contact {self.provider.base_url}. Only this computer is allowed.")
        return HTTPConnection(host, port, timeout=self.start_timeout), base_path.rstrip("/")

    def _network_error(self, error: Exception) -> DoorError:
        url = self.provider.base_url
        if isinstance(error, ConnectionRefusedError):
            return DoorError(f"Korvin cannot reach the model service at {url}. Is Ollama running?")
        if isinstance(error, TimeoutError):
            return DoorError(
                f"The model service at {url} did not answer in time. "
                "The first answer after the service starts can be slow while the model loads. Please try again."
            )
        return DoorError(f"Korvin lost contact with the model service at {url}: {error}")


def send(connection: HTTPConnection, method: str, path: str, payload: dict | None, timeout: float) -> HTTPResponse:
    """Send one request and return the response. Refuse redirects and error replies.

    The connection's own timeout covers the wait for the reply to begin.
    After that, the shorter timeout given here covers each read.
    """
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
    # Keep the socket now: the connection can let go of it when the response arrives.
    sock = connection.sock
    response = connection.getresponse()
    sock.settimeout(timeout)
    if 300 <= response.status < 400:
        raise DoorError("The model service tried to send Korvin to another address. Korvin does not follow redirects.")
    if response.status != 200:
        details = error_text(response.read(ERROR_READ_LIMIT))
        if response.status == 400 and "does not support tools" in details:
            raise ToolsNotSupported("This model cannot use tools.")
        raise DoorError(f"The model service returned error {response.status}: {details[:ERROR_SHOW_LIMIT]}")
    return response


def stream_lines(response: HTTPResponse) -> Generator[str, None, None]:
    """Yield each line of the stream as text. Refuse a line that is longer than LINE_LIMIT."""
    while raw_line := response.readline(LINE_LIMIT + 1):
        if len(raw_line) > LINE_LIMIT:
            raise DoorError("The model service sent a line that is too long. Korvin stopped reading the answer.")
        yield decode(raw_line).rstrip("\r\n")


def decode(raw: bytes) -> str:
    """Turn bytes from the service into text."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DoorError("The model service sent text that is not valid UTF-8.") from None


def parse_json(text: str) -> object:
    """Read JSON text from the service."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise DoorError(UNREADABLE) from None


def is_count(value: object) -> bool:
    """Return True for a whole number that is 0 or more. bool is a kind of int in Python, so refuse it by name."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def model_names(data: object) -> list[str]:
    """Return the "id" of each model in a /models reply."""
    try:
        # Ollama sends "data": null, not an empty list, when no model is installed.
        names = [entry["id"] for entry in data["data"] or []]
    except (KeyError, TypeError):
        raise DoorError(UNREADABLE) from None
    if not all(isinstance(name, str) for name in names):
        raise DoorError(UNREADABLE)
    return names


def delta_from_line(line: str) -> dict | Usage:
    """Return the "delta" object of one stream line: the new part of the reply.

    The last line before the end can hold only the token counts. Then return them as Usage.
    """
    if not line.startswith("data: "):
        raise DoorError(UNREADABLE)
    event = parse_json(line.removeprefix("data: "))
    if error_message(event):
        raise DoorError(f"The model service reported an error: {error_message(event)}")
    if isinstance(event, dict) and event.get("choices") == [] and isinstance(event.get("usage"), dict):
        tokens = event["usage"].get("prompt_tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            raise DoorError(UNREADABLE)
        return Usage(tokens)
    try:
        delta = event["choices"][0]["delta"]
    except (KeyError, IndexError, TypeError):
        raise DoorError(UNREADABLE) from None
    if not isinstance(delta, dict):
        raise DoorError(UNREADABLE)
    return delta


def pieces_from_delta(delta: dict) -> list[Piece]:
    """Return the thinking and answer pieces in one delta. A delta can have none."""
    # A reasoning model sends its thinking in "reasoning", apart from the answer in "content".
    texts = [("thinking", delta.get("reasoning")), ("answer", delta.get("content"))]
    if not all(text is None or isinstance(text, str) for _kind, text in texts):
        raise DoorError(UNREADABLE)
    return [Piece(kind, text) for kind, text in texts if text]


def add_call_parts(calls: dict[int, dict], delta: dict) -> None:
    """Add the tool call parts in one delta to the calls, by index.

    The name and the arguments of a call can arrive in pieces, so Korvin joins the pieces.
    """
    parts = delta.get("tool_calls")
    if parts is not None and not isinstance(parts, list):
        raise DoorError(UNREADABLE)
    for part in parts or []:
        if not isinstance(part, dict) or part.get("type") not in (None, "function"):
            raise DoorError(UNREADABLE)
        index, function = part.get("index"), part.get("function", {})
        # bool is a kind of int in Python, so refuse it by name.
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or not isinstance(function, dict):
            raise DoorError(UNREADABLE)
        call_id, name, arguments = part.get("id"), function.get("name"), function.get("arguments")
        if not all(value is None or isinstance(value, str) for value in (call_id, name, arguments)):
            raise DoorError(UNREADABLE)
        call = calls.setdefault(index, {"id": None, "name": "", "arguments": ""})
        if call_id is not None and call["id"] not in (None, call_id):
            raise DoorError(UNREADABLE)  # two different ids for one call
        call["id"] = call_id or call["id"]
        call["name"] += name or ""
        call["arguments"] += arguments or ""


def finished_calls(calls: dict[int, dict]) -> list[ToolCall]:
    """Return the joined tool calls in index order. Give an id to a call that has none."""
    if not all(call["name"] for call in calls.values()):
        raise DoorError("The model service sent a tool call without a name.")
    ordered = sorted(calls.items())
    return [ToolCall(call["id"] or f"call_{index}", call["name"], call["arguments"]) for index, call in ordered]


def error_message(data: object) -> str:
    """Return the message in an OpenAI-style error object, or "" if there is none."""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        error = error.get("message")
    return error if isinstance(error, str) else ""


def error_text(raw: bytes) -> str:
    """Return a readable error text from the body of an error reply. The caller shortens it to show it."""
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        text = error_message(json.loads(text)) or text
    except json.JSONDecodeError:
        pass
    return text or "no details"
