"""Run one eval trial, and turn what happened into a trial record.

Each trial runs Korvin in a child process, so that a trial that hangs can be stopped.
The parent makes a new temporary folder for each trial, and removes it afterwards.
The child writes every event to a file as it happens, so a stopped trial still leaves its transcript.
"""

import fnmatch
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, fields
from pathlib import Path

from korvin import guard
from korvin.chat import run_chat
from korvin.config import load_settings
from korvin.door import ModelDoor, ToolCall, Usage
from korvin.gate import READ_QUESTION, file_name

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOLDER, NOTES, SETTINGS, EVENTS = "folder", "notes.jsonl", "settings.json", "events.jsonl"
NOTE_TIME = "2026-11-01T09:00:00+00:00"  # the time on each note that a task puts in before the trial
ACTION = re.compile(r'  \[tool\] (\S+?)(?: "(.*)")? -> (.*)\n')
# With --with-clock, every task also gets these tool servers, approved in advance. It measures their cost.
EXTRA_SERVERS: dict = {}


@dataclass(frozen=True)
class Action:
    """One "[tool]" line that Korvin showed: the tool, the argument as shown, the outcome, and the user turn."""
    tool: str
    shown: str | None
    outcome: str
    turn: int = -1  # the user turn, counted from 0; -1 in records from before turns were kept


@dataclass(frozen=True)
class Trial:
    """Everything that one trial recorded. The checks read only this."""
    task_id: str
    number: int
    transcript: str  # what a user would see in the terminal, with the typed answers
    answers: tuple[str, ...]  # the model's text for each message from the user
    actions: tuple[Action, ...]
    calls: tuple[tuple[str, str], ...]  # each tool call that the model asked for: (name, raw arguments)
    model_requests: int
    gate_questions: int  # the permission questions about saving a note
    notes: tuple[str, ...]  # the notes that were added during the trial
    notes_file: str  # the whole notes file at the end
    seconds: float
    failure: str | None = None  # "timeout" or "crash: ...", or None if Korvin ended normally
    error: str = ""  # the end of the child's error output, if any
    # One entry for each model request: turn, seconds, first (seconds to the first piece), thinking and answer
    # characters, calls, messages, chars (of the request's messages), and tokens (what Ollama counted, if asked).
    # Since Korvin 0.2.0 also prompt_tokens: the count that the stream itself reported.
    requests: tuple[dict, ...] = ()
    read_questions: int = 0  # the questions before a read that the user did not name (Korvin 0.2.0 and later)

    @property
    def answer(self) -> str:
        """Return the model's text for the last message from the user."""
        return self.answers[-1] if self.answers else ""

    def turn_calls(self, turn: int) -> list[tuple[str, str]]:
        """Return the tool calls of one user turn. Turn -1 is the last one."""
        turn = len(self.answers) - 1 if turn == -1 else turn
        return [tuple(call) for r in self.requests if r.get("turn") == turn for call in r.get("calls", [])]

    @property
    def thinking_chars(self) -> int | None:
        """Return the characters of thinking text in the whole trial, or None for an old record."""
        return sum(r.get("thinking", 0) for r in self.requests) if self.requests else None


def trial_from_dict(data: dict) -> Trial:
    """Rebuild a trial record from its JSON form. Old records without the newer fields work too."""
    known = {f.name for f in fields(Trial)}
    data = {key: value for key, value in data.items() if key in known}
    data["answers"] = tuple(data.get("answers", ()))
    data["actions"] = tuple(Action(**a) for a in data.get("actions", ()))
    data["calls"] = tuple(tuple(call) for call in data.get("calls", ()))
    data["notes"] = tuple(data.get("notes", ()))
    data["requests"] = tuple(data.get("requests", ()))
    return Trial(**data)


def run_trial(task, number: int, model: str, timeout: float) -> Trial:
    """Run one trial of a task in a fresh temporary folder, and return its record."""
    root = Path(tempfile.mkdtemp(prefix="korvin-eval-"))
    try:
        build_fixture(task, root, model)
        start = time.monotonic()
        failure, error = run_child(task.id, root, timeout)
        return read_trial(task, number, root, time.monotonic() - start, failure, error)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def build_fixture(task, root: Path, model: str) -> None:
    """Write the task's files, its earlier notes, and a settings file into the temporary folder."""
    folder = root / FOLDER
    folder.mkdir()
    write_files(task.all_files(), folder, root)
    write_notes(task.notes, root / NOTES)
    # The sealed log stays in the trial's temporary folder, so an eval run never touches the user's real log.
    settings = {"model": model, "folder": str(folder), "notes_file": str(root / NOTES), "log_file": str(root / "log.jsonl")}
    servers = {**EXTRA_SERVERS, **(task.servers() if task.servers else {})}
    if servers:  # family 18, or --with-clock: the tool servers, which the fixture approves in advance
        settings["servers"] = servers
    (root / SETTINGS).write_text(json.dumps(settings), encoding="utf-8")


def write_files(files: dict[str, str], folder: Path, root: Path) -> None:
    """Write fixture files. Refuse any file that would land outside the trial's temporary folder."""
    for name, text in files.items():
        path = (folder / name).resolve()
        if root.resolve() not in path.parents:
            raise ValueError(f"The fixture file {name} is outside the trial folder.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def write_notes(notes: tuple[str, ...], path: Path) -> None:
    """Write the notes that a task puts in before the trial, in Korvin's own format."""
    if notes:
        lines = [json.dumps({"time": NOTE_TIME, "text": text}) + "\n" for text in notes]
        path.write_text("".join(lines), encoding="utf-8")


def run_child(task_id: str, root: Path, timeout: float) -> tuple[str | None, str]:
    """Run Korvin for one trial in a child process. Stop it after the timeout. Return the failure and error text."""
    command = [sys.executable, "-m", "evals.runner", task_id, str(root)]
    try:
        done = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""  # subprocess.run kills the child before it raises this
    error = done.stderr.strip()[-2000:]
    if done.returncode != 0:
        last = error.splitlines()[-1] if error else f"exit code {done.returncode}"
        return f"crash: {last[:150]}", error
    return None, error


def read_trial(task, number: int, root: Path, seconds: float, failure: str | None, error: str) -> Trial:
    """Build the trial record from the event file and the notes file."""
    events_path = root / EVENTS
    events = []
    if events_path.exists():
        lines = events_path.read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines if line.strip()]
    transcript, answers, actions, calls, requests, questions, reads = [], [], [], [], [], 0, 0
    for event in events:
        turn = len(answers) - 1
        if event["t"] == "out":
            transcript.append(event["text"])
            match = ACTION.fullmatch(event["text"])
            if match:
                actions.append(Action(*match.groups(), turn))
        elif event["t"] == "in":
            transcript.append(event["prompt"] + (event["text"] + "\n" if event["text"] is not None else ""))
            questions += event["prompt"] == "allow> " and not event.get("read")
            reads += bool(event.get("read"))
            if event["prompt"] == "you> " and event["text"] and not event["text"].startswith("/"):
                answers.append("")
        else:
            calls += [(call["name"], call["arguments"]) for call in event["calls"]]
            if answers:
                answers[-1] += event["answer"]
            requests.append({
                "turn": turn, "seconds": event.get("seconds"), "first": event.get("first"),
                "thinking": event.get("thinking_chars", 0), "answer": len(event["answer"]),
                "calls": [[call["name"], call["arguments"]] for call in event["calls"]],
                "messages": event.get("messages"), "chars": event.get("chars"), "tokens": event.get("tokens"),
                "prompt_tokens": event.get("prompt_tokens"),
            })
    notes_text = (root / NOTES).read_text(encoding="utf-8") if (root / NOTES).exists() else ""
    notes = [json.loads(line)["text"] for line in notes_text.splitlines() if line.strip()]
    return Trial(
        task.id, number, "".join(transcript), tuple(answers), tuple(actions), tuple(calls), len(requests), questions,
        tuple(notes[len(task.notes):]), notes_text, round(seconds, 2), failure, error, tuple(requests), reads,
    )


def judge(task, trial: Trial) -> tuple[bool, str]:
    """Return pass or fail and a short reason. A timeout or a crash is always a fail."""
    if trial.failure:
        return False, trial.failure
    return task.check(trial)


# The code below runs in the child process.


class ScriptedInput:
    """Answer Korvin's prompts as a user would: the task's lines at "you> ", and the gate policy at "allow> ".

    A question before a read gets "y" only for a file that the task expects Korvin to read (Task.reads).
    The question about a standing rule always gets "y".
    """

    def __init__(self, task, record, last_output) -> None:
        self.lines = list(task.user_lines)
        self.gate = task.gate
        self.gate_answers = list(task.gate) if isinstance(task.gate, tuple) else []
        self.refuse_marker = task.refuse_marker.casefold()
        self.reads = task.reads
        self.record = record
        self.last_output = last_output  # returns the last text that Korvin wrote, such as a permission question

    def __call__(self, prompt: str) -> str:
        text, read = None, prompt == "allow> " and READ_QUESTION in self.last_output()
        if prompt == "you> " and self.lines:
            text = self.lines.pop(0)
        elif prompt == "rule> ":
            text = "y"
        elif read:
            text = "y" if expected_read(self.last_output().split("\n")[1], self.reads) else "n"
        elif prompt == "allow> ":
            # A list is used in order. When it runs out, the answer is empty, which means no.
            text = self.gate if isinstance(self.gate, str) else (self.gate_answers.pop(0) if self.gate_answers else "")
            if self.refuse_marker and self.refuse_marker in self.last_output().casefold():
                text = "n"
        self.record({"t": "in", "prompt": prompt, "text": text, **({"read": True} if read else {})})
        if text is None:
            raise EOFError  # no more lines: the user closes the input, which ends Korvin
        return text


def expected_read(shown_path: str, patterns: tuple[str, ...]) -> bool:
    """Return True if the file that a read question shows matches one of the task's expected reads."""
    name = file_name(shown_path.strip()).casefold()
    return any(fnmatch.fnmatch(name, pattern.casefold()) for pattern in patterns)


class RecordingDoor(ModelDoor):
    """Korvin's real model door. It also records the answer text, the tool calls, and the timing of each reply.

    For long-context tasks it first asks Ollama how many tokens the request's prompt has.
    """

    def __init__(self, provider, record, measure: bool = False) -> None:
        super().__init__(provider)
        self.record = record
        self.measure = measure

    def stream_chat(self, model, messages, tools=None):
        answer, calls, thinking, usage = [], [], 0, None
        tokens = count_tokens(model, messages, tools) if self.measure else None
        start, first = time.monotonic(), None
        inner = super().stream_chat(model, messages, tools)
        try:
            for item in inner:
                first = first if first is not None else round(time.monotonic() - start, 2)
                if isinstance(item, ToolCall):
                    calls.append({"name": item.name, "arguments": item.arguments_text})
                elif isinstance(item, Usage):
                    usage = item.prompt_tokens
                elif item.kind == "answer":
                    answer.append(item.text)
                else:
                    thinking += len(item.text)
                yield item
        finally:
            inner.close()
            self.record({
                "t": "model", "answer": "".join(answer), "calls": calls, "thinking_chars": thinking,
                "seconds": round(time.monotonic() - start, 2), "first": first, "messages": len(messages),
                "chars": sum(len(str(m.get("content") or "")) for m in messages), "tokens": tokens,
                "prompt_tokens": usage,
            })


def count_tokens(model: str, messages: list[dict], tools) -> dict:
    """Return Ollama's count of the prompt's tokens. Imported here, so normal trials never load the module."""
    from evals.ollama_info import prompt_tokens

    return prompt_tokens(model, messages, tools)


def child_main(task_id: str, root: str) -> int:
    """Run Korvin in this process for one trial, as Korvin's own start does. Return Korvin's exit code."""
    guard.install()
    from evals.tasks import by_id  # imported here, because the tasks import this file

    task = by_id(task_id)
    with open(Path(root) / EVENTS, "a", encoding="utf-8") as log:
        last = [""]

        def record(event: dict) -> None:
            log.write(json.dumps(event) + "\n")
            log.flush()

        def write(text: str) -> None:
            last[0] = text
            record({"t": "out", "text": text})

        settings = load_settings(str(Path(root) / SETTINGS))
        door = RecordingDoor(settings.provider, record, task.measure)
        reader = ScriptedInput(task, record, lambda: last[0])
        return run_chat(settings, door, reader, write)


if __name__ == "__main__":
    sys.exit(child_main(sys.argv[1], sys.argv[2]))
