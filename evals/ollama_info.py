"""Check that Ollama is ready, and read facts about the loaded model.

This is the only evals file that uses the network, apart from Korvin's own model door.
It talks to Ollama's local API on 127.0.0.1 only.
It never pulls, creates, deletes, or stops a model, and it never changes a load setting.
"""

import json
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException

from korvin.config import DEFAULT_BASE_URL, Provider
from korvin.door import DoorError, ModelDoor

HOST, PORT = "127.0.0.1", 11434
MIN_CONTEXT = 65_536  # D-002: the 64k context is a fixed condition
WARM_UP_LIMIT = 4_000  # the most characters of the warm-up reply, thinking included
COUNT_TIMEOUT = 600  # seconds; a 64k prompt that is not in the cache takes over a minute to read


class NotReady(Exception):
    """Ollama or the model is not ready for an eval run."""


@dataclass(frozen=True)
class ModelInfo:
    """Facts about the loaded model, from Ollama's /api/ps."""
    name: str
    digest: str
    context_length: int
    size: int
    size_vram: int

    @property
    def gpu_share(self) -> float:
        """Return the part of the model that is on the graphics card, from 0 to 1."""
        return self.size_vram / self.size if self.size else 0.0


def same_model(name: str, model: str) -> bool:
    """Return True if an Ollama name is the model, such as "qwen:latest" for "qwen"."""
    return name in (model, f"{model}:latest")


def call_json(method: str, path: str, payload: dict | None = None, timeout: float = 10) -> dict:
    """Send one request to Ollama's local API and return the JSON object."""
    connection = HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        text = response.read().decode("utf-8", errors="replace")
        if response.status != 200:
            raise NotReady(f"Ollama answered {path} with error {response.status}: {text[:300]}")
        return json.loads(text)
    finally:
        connection.close()


def get_json(path: str) -> dict:
    """Send a GET request to Ollama's local API and return the JSON object."""
    return call_json("GET", path)


def version() -> str:
    """Return Ollama's version, such as "0.40.17"."""
    return str(get_json("/api/version").get("version", "unknown"))


def show(model: str) -> dict:
    """Return the model's stored parameters and details. This does not load the model."""
    data = call_json("POST", "/api/show", {"model": model})
    return {"parameters": data.get("parameters", ""), "details": data.get("details", {}),
            "capabilities": data.get("capabilities", [])}


def loaded_model(model: str) -> ModelInfo | None:
    """Return the facts about the model if Ollama has it loaded now, or None."""
    for entry in get_json("/api/ps").get("models") or []:
        if same_model(entry.get("name", ""), model) or same_model(entry.get("model", ""), model):
            return ModelInfo(
                entry.get("name", model), entry.get("digest", ""), int(entry.get("context_length", 0)),
                int(entry.get("size", 0)), int(entry.get("size_vram", 0)),
            )
    return None


def loaded_names() -> list[str]:
    """Return the names of all models that Ollama has loaded now."""
    return [entry.get("name", "?") for entry in get_json("/api/ps").get("models") or []]


def check_ready(model: str) -> ModelInfo:
    """Check that Ollama runs, lists the model, and loads it with a 64k context. Return the model facts."""
    door = ModelDoor(Provider("local", DEFAULT_BASE_URL, False))
    try:
        names = door.list_models()
        if not any(same_model(name, model) for name in names):
            raise NotReady(f'Ollama does not list the model "{model}". It lists: {", ".join(names) or "nothing"}.')
        others = [name for name in loaded_names() if not same_model(name, model)]
        if others:
            raise NotReady(f"Another model is loaded: {', '.join(others)}. Only one model may be loaded at a time.")
        # One small request loads the model the same way that Korvin loads it.
        # The model can think in a loop until the context is full, which took 15 minutes on 2026-11-24.
        # So the warm-up stops after WARM_UP_LIMIT characters. Closing the stream stops the work in Ollama.
        stream, received = door.stream_chat(model, [{"role": "user", "content": "Say OK."}]), 0
        try:
            for piece in stream:
                received += len(getattr(piece, "text", ""))
                if received > WARM_UP_LIMIT:
                    break
        finally:
            stream.close()
        info = loaded_model(model)
    except (DoorError, OSError, HTTPException, ValueError) as error:
        raise NotReady(f"Ollama is not ready at {DEFAULT_BASE_URL}: {error}") from None
    if info is None:
        raise NotReady(f'Ollama did not keep the model "{model}" loaded after the warm-up request.')
    if info.context_length < MIN_CONTEXT:
        raise NotReady(
            f"The model's context is {info.context_length:,} tokens. "
            f"The evals need at least {MIN_CONTEXT:,} tokens (D-002), so they stop here."
        )
    return info


def native_messages(messages: list[dict]) -> list[dict]:
    """Turn Korvin's OpenAI-style messages into the shape of Ollama's own /api/chat.

    The only differences: tool call arguments are a JSON object there, and a tool result names its tool.
    """
    names: dict[str, str] = {}
    result = []
    for message in messages:
        message = dict(message)
        calls = []
        for index, call in enumerate(message.get("tool_calls") or []):
            function = call["function"]
            names[call.get("id", "")] = function["name"]
            try:
                arguments = json.loads(function["arguments"])
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            calls.append({"id": call.get("id"), "function": {
                "index": index, "name": function["name"], "arguments": arguments if isinstance(arguments, dict) else {}}})
        if calls:
            message["tool_calls"] = calls
        if message.get("role") == "tool":
            message["tool_name"] = names.get(message.get("tool_call_id", ""), "")
        result.append(message)
    return result


def prompt_tokens(model: str, messages: list[dict], tools: list[dict] | None) -> dict:
    """Ask Ollama how many tokens a request's prompt has. Return the numbers that the server reports.

    The request uses Ollama's own /api/chat and stops after one new token.
    It sends no load setting, so Ollama keeps the loaded model as it is.
    The answer holds "prompt_tokens", "seconds", and "load_seconds", or "error" if the request failed.
    """
    payload = {"model": model, "messages": native_messages(messages), "stream": False, "options": {"num_predict": 1}}
    if tools:
        payload["tools"] = tools
    try:
        data = call_json("POST", "/api/chat", payload, timeout=COUNT_TIMEOUT)
    except (NotReady, OSError, HTTPException, ValueError) as error:
        return {"error": str(error)[:300]}
    return {
        "prompt_tokens": data.get("prompt_eval_count"),
        "seconds": round(data.get("total_duration", 0) / 1e9, 2),
        "prompt_seconds": round(data.get("prompt_eval_duration", 0) / 1e9, 2),
        "load_seconds": round(data.get("load_duration", 0) / 1e9, 2),
    }
