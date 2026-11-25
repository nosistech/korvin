"""Run one single-decision trial: one model call on a fixed conversation, graded on the reply alone.

The conversation uses Korvin's real system prompt, tool schemas, and message format.
Earlier tool results come from Korvin's real tool code, run on the case's files in a temporary folder.
No tool runs after the reply. The check reads only the answer text and the tool calls.
"""

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, fields
from pathlib import Path

from evals.runner import FOLDER, NOTES, RecordingDoor, write_files, write_notes
from korvin import tools
from korvin.chat import TOO_LONG_THINKING, Session, assistant_message, new_conversation, run_call, stream_reply
from korvin.config import DEFAULT_BASE_URL, Provider, Settings, check_folder
from korvin.door import ToolCall
from korvin.gate import Gate

PROVIDER = Provider("local", DEFAULT_BASE_URL, False)


@dataclass(frozen=True)
class Reply:
    """Everything that one single-decision trial recorded. The checks read only this."""
    case_id: str
    number: int
    messages: tuple[dict, ...]  # the conversation that the model got, the system message included
    text: str  # the answer text of the reply
    calls: tuple[tuple[str, str], ...]  # each tool call in the reply: (name, raw arguments)
    thinking_chars: int
    seconds: float
    first: float | None = None  # seconds to the first piece of the reply
    failure: str | None = None  # "thinking limit" or "error: ...", or None
    output: str = ""  # what Korvin printed while the reply arrived

    @property
    def answer(self) -> str:
        return self.text

    def parsed(self) -> list[tuple[str, dict]]:
        """Return each call with its arguments as a dictionary. Arguments that are not a JSON object become {}."""
        result = []
        for name, raw in self.calls:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = {}
            result.append((name, value if isinstance(value, dict) else {}))
        return result

    def conversation(self) -> str:
        """Return the text of every message after the system message, tool results included."""
        return "\n".join(str(m.get("content") or "") for m in self.messages[1:])


def reply_from_dict(data: dict) -> Reply:
    """Rebuild a reply record from its JSON form."""
    known = {f.name for f in fields(Reply)}
    data = {key: value for key, value in data.items() if key in known}
    data["messages"] = tuple(data.get("messages", ()))
    data["calls"] = tuple(tuple(call) for call in data.get("calls", ()))
    return Reply(**data)


def build_messages(case, settings: Settings) -> list[dict]:
    """Build the case's conversation. Each earlier tool call runs through Korvin's own run_call."""
    answers: list[str] = []
    sink: list[str] = []
    gate = Gate(lambda _prompt: answers.pop(0) if answers else "", sink.append)
    session = Session(settings, None, gate, sink.append)
    messages = new_conversation(True)
    for number, step in enumerate(case.prompt, 1):
        if step[0] in ("user", "assistant"):
            messages.append({"role": step[0], "content": step[1]})
            continue
        _kind, name, value, *gate_answers = step
        call = ToolCall(f"call_{number}", name, json.dumps({tools.TOOLS[name].argument: value}))
        answers[:] = gate_answers
        result = run_call(session, call)
        gate.outside_text |= result.outside  # as in a real turn, so a later unexpected read gets the read question
        messages +=[assistant_message("", [call]), {"role": "tool", "tool_call_id": call.id, "content": result.text}]
    return messages


def run_case(case, number: int, model: str) -> Reply:
    """Run one trial of a decision case in a fresh temporary folder, and return its record."""
    root = Path(tempfile.mkdtemp(prefix="korvin-decision-"))
    try:
        (root / FOLDER).mkdir()
        write_files(case.files, root / FOLDER, root)
        write_notes(case.notes, root / NOTES)
        settings = Settings(model, PROVIDER, check_folder(str(root / FOLDER)), root / NOTES)
        messages = build_messages(case, settings)
        return ask_once(case.id, number, settings, messages)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def ask_once(case_id: str, number: int, settings: Settings, messages: list[dict]) -> Reply:
    """Send the conversation once through Korvin's own stream_reply, and record the reply."""
    events: list[dict] = []
    output: list[str] = []
    door = RecordingDoor(settings.provider, events.append)
    session = Session(settings, door, Gate(lambda _prompt: "", output.append), output.append)
    start = time.monotonic()
    got = stream_reply(session, list(messages), tools.SCHEMAS)
    seconds = round(time.monotonic() - start, 2)
    event = events[-1] if events else {"answer": "", "calls": [], "thinking_chars": 0}
    printed = "".join(output)
    failure = None
    if got is None:
        failure = "thinking limit" if TOO_LONG_THINKING in printed else f"error: {printed.strip()[:150]}"
    calls = tuple((call["name"], call["arguments"]) for call in event["calls"])
    return Reply(case_id, number, tuple(messages), event["answer"], calls, event["thinking_chars"], seconds,
                 event.get("first"), failure, printed)


def judge_reply(case, reply: Reply) -> tuple[bool, str]:
    """Return pass or fail and a short reason. A failed request is always a fail."""
    if reply.failure:
        return False, reply.failure
    return case.check(reply)
