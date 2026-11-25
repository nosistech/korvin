"""The record of a run: versions, settings, and fingerprints, so that two runs can be compared fairly.

A fingerprint is a SHA-256 hash. Two runs with the same fingerprint used the same text.
"""

import hashlib
import json
import platform
import sys
from pathlib import Path

from korvin import __version__, chat, door, rules, tools

EVALS_DIR = Path(__file__).resolve().parent
KNOWN_GAPS = (
    "Runs are not seeded. Korvin's model door sends no seed, and the evals do not change Korvin.",
    "Tokens per second are not recorded. Since Korvin 0.2.0 each request records its prompt tokens, but no speed.",
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def describe(item) -> dict:
    """Return the data of a task or a case that decides what the model sees, for the task fingerprint."""
    data = {"id": item.id, "kind": item.kind, "family": item.family_number, "steps": item.steps,
            "notes": list(item.notes), "info": {k: str(v) for k, v in item.info.items()}}
    if item.target == "decision":
        data.update(prompt=[list(step) for step in item.prompt], files=item.files)
    else:
        files = item.all_files()
        data.update(lines=list(item.user_lines), gate=item.gate, refuse=item.refuse_marker, needs=list(item.needs),
                    facts=[str(f) for f in item.facts], files={k: sha(v) for k, v in sorted(files.items())},
                    reads=list(item.reads))
    return data


def task_fingerprint(items) -> str:
    """Return one fingerprint for the data of the chosen tasks and cases."""
    return sha(json.dumps([describe(item) for item in items], sort_keys=True))


def code_fingerprint() -> str:
    """Return one fingerprint for the source of the evals, where the checks live."""
    paths = sorted(p for p in EVALS_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    return sha("\n".join(p.relative_to(EVALS_DIR).as_posix() + "\n" + p.read_text("utf-8") for p in paths))


def tunables() -> dict:
    """Return the values of Korvin's tunable limits that a run depends on."""
    names = ("MODEL_CALL_LIMIT", "RETRY_EMPTY_ANSWER", "THINKING_LIMIT", "REPLY_CALL_LIMIT", "SHOWN_LIMIT",
             "ANSWER_RESERVE", "FULL_WARNING")
    limits = ("LIST_LIMIT", "READ_LIMIT", "NOTE_LIMIT", "FIND_LIMIT", "RESULT_LIMIT")
    return {**{n: getattr(chat, n) for n in names}, **{n: getattr(tools, n) for n in limits},
            "RULE_LIMIT": rules.RULE_LIMIT, "RULE_CHARS": rules.RULE_CHARS, "SAMPLING": door.SAMPLING}


def static_meta(command: list[str]) -> dict:
    """Return the parts of the run record that need no model service."""
    return {
        "korvin_version": __version__, "python": sys.version.split()[0], "os": platform.platform(),
        "command": " ".join(command),
        "prompt_fingerprint": sha(chat.SYSTEM_PROMPT),
        "schemas_fingerprint": sha(json.dumps(tools.SCHEMAS, sort_keys=True)),
        "code_fingerprint": code_fingerprint(), "tunables": tunables(), "known_gaps": list(KNOWN_GAPS),
    }
