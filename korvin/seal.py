"""Keep the sealed log, and check it.

The log has one JSON line for each event: a number, a UTC time, the event, its details, and a seal.
The seal is the SHA-256 of the previous line's seal and this line's content, in one fixed JSON form.
So a changed line breaks its own seal, and a removed or inserted line breaks the chain after it.
The log holds no file contents or chat text. It keeps up to 60 characters of each tool argument and standing rule.
A person who can rewrite the whole file can also rebuild every seal. Only a seal kept elsewhere shows that.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from korvin.gate import clean

START = "0" * 64  # the "previous seal" of the first line
TAIL_BYTES = 65_536  # Korvin reads this much of the end of the log to find the last line
FIXED = ("seq", "time", "event", "seal")  # the keys of every line; the other keys are the details
NOT_KEPT = "Korvin cannot keep its sealed log ({reason}), so this session has no record. The chat goes on.\n"
DAMAGED = "the last line of the log is damaged. Type python -m korvin check to see where"
CLOSING = "Last seal of the log: {seal}\nKeep it elsewhere. Later, python -m korvin check --seal VALUE compares it.\n"
NO_LOG = "There is no sealed log at {path} yet, so there is nothing to check.\n"
INTACT = (
    "The sealed log is intact.\n  File: {path}\n  Entries: {count:,}, from {first} to {last} (UTC)\n"
    "  Last seal: {seal}\n"
    "Each entry matches its seal and the entry before it. So no entry was changed, removed, or inserted,\n"
    "unless someone also rebuilt every seal after it. Anyone who can write the file can do that,\n"
    "or cut entries from the end. To rule that out, compare the last seal with a copy that you keep elsewhere.\n"
)
BROKEN = (
    "The sealed log is BROKEN at line {number}: {problem}.\n  File: {path}\n"
    "  The {good:,} lines before it are intact. Their last seal: {seal}\n"
)
KEPT_FOUND = "The seal that you kept is entry {number:,}, so entries 1 to {number:,} are unchanged since then.\n"
KEPT_MISSING = "The seal that you kept is not in the log. The log was rewritten, or the seal is from another log.\n"


def canonical(entry: dict) -> str:
    """Return the one fixed JSON form of an entry: sorted keys, no spaces, ASCII only."""
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def seal_of(previous: str, entry: dict) -> str:
    """Return the seal of an entry: the SHA-256 of the previous seal followed by the entry's fixed JSON form."""
    return hashlib.sha256((previous + canonical(entry)).encode("ascii")).hexdigest()


class Log:
    """Add entries to the sealed log. A failed write never stops the chat. Korvin tells the user once."""

    def __init__(self, path: Path | None, write: Callable[[str], None] = lambda _text: None) -> None:
        self.path = path  # None means: keep no log
        self.write = write
        self.seal = ""  # the seal of the last entry that this session added

    def add(self, event: str, **details: object) -> None:
        """Add one entry. If that fails, stop the log for this session and tell the user."""
        if self.path is None:
            return
        try:
            self.seal = append(self.path, event, details)
        except (OSError, ValueError) as error:
            self.path = None
            self.write(clean(NOT_KEPT.format(reason=getattr(error, "strerror", None) or error)))

    def closing(self) -> str:
        """Return the closing words with the last seal, or "" if this session added no entry."""
        return CLOSING.format(seal=self.seal) if self.seal and self.path else ""


def append(path: Path, event: str, details: dict) -> str:
    """Add one sealed entry to the end of the log, and return its seal."""
    number, previous = last_entry(path)
    time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"seq": number + 1, "time": time, "event": event, **details}
    seal = seal_of(previous, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="ascii", newline="\n") as file:
        file.write(canonical({**entry, "seal": seal}) + "\n")
    return seal


def last_entry(path: Path) -> tuple[int, str]:
    """Return the number and the seal of the last entry, or (0, START) when the log has no entry yet.

    Korvin reads the end of the file before each entry, so two sessions at once still make one chain.
    """
    if not path.exists():
        return 0, START
    with open(path, "rb") as file:
        file.seek(max(0, file.seek(0, 2) - TAIL_BYTES))
        tail = file.read()
    if not tail:
        return 0, START
    if not tail.endswith(b"\n"):
        raise ValueError(DAMAGED)
    entry = parse(tail.splitlines()[-1], DAMAGED)
    return entry["seq"], entry["seal"]


def parse(line: bytes, problem: str = "it is not a readable entry") -> dict:
    """Read one line of the log. Refuse a line that is not an entry with a number and a seal."""
    try:
        entry = json.loads(line)
    except ValueError:
        entry = None
    seq = entry.get("seq") if isinstance(entry, dict) else None
    if not isinstance(seq, int) or isinstance(seq, bool) or not isinstance(entry.get("seal"), str):
        raise ValueError(problem)
    return entry


def verified(line: bytes, number: int, previous: str) -> dict:
    """Return the entry on one line. Raise ValueError with the reason if it does not fit the chain."""
    entry = parse(line)
    if line != canonical(entry).encode("ascii"):
        raise ValueError("its text is not in the fixed form that Korvin writes, so someone edited it")
    if entry["seq"] != number:
        raise ValueError(f"it says that it is entry {entry['seq']}, so an entry before it was removed or inserted")
    if entry["seal"] != seal_of(previous, {key: value for key, value in entry.items() if key != "seal"}):
        raise ValueError("its seal does not match. It was changed, or an entry before it was removed or inserted")
    return entry


def check(path: Path, kept: str | None = None) -> tuple[bool, str]:
    """Check every seal in the log, and a kept seal if given. Return the result and a plain report."""
    if not path.is_file():
        return False, clean(NO_LOG.format(path=path))
    *lines, rest = path.read_bytes().split(b"\n")  # every entry ends with a newline, so "rest" should be empty
    entries: list[dict] = []
    try:
        for number, line in enumerate(lines, 1):
            entries.append(verified(line, number, entries[-1]["seal"] if entries else START))
        if rest:
            raise ValueError("it does not end with a line break, so it may be cut off")
    except ValueError as error:
        good, seal = len(entries), entries[-1]["seal"] if entries else START
        return False, clean(BROKEN.format(number=good + 1, problem=error, path=path, good=good, seal=seal))
    if not entries:
        return False, clean(NO_LOG.format(path=path))
    first, last = (str(entries[index]["time"]).replace("T", " ").rstrip("Z") for index in (0, -1))
    report = INTACT.format(path=path, count=len(entries), first=first, last=last, seal=entries[-1]["seal"])
    if kept is None:
        return True, clean(report)
    found = [number for number, entry in enumerate(entries, 1) if entry["seal"] == kept.strip().lower()]
    return bool(found), clean(report + (KEPT_FOUND.format(number=found[0]) if found else KEPT_MISSING))


def table(path: Path, count: int) -> str:
    """Return the last entries of the log as a readable table. This does not check the seals."""
    if not path.is_file():
        return clean(NO_LOG.replace("check", "show").format(path=path))
    every = path.read_bytes().splitlines()
    lines = every[-max(count, 1):]
    rows = [f"The last {len(lines):,} of {len(every):,} entries in {path}:"]
    rows.append(f"{'#':>6}  {'Time (UTC)':19}  {'Event':17} Details")
    for line in lines:
        try:
            entry = parse(line)
        except ValueError:
            rows.append(f"{'?':>6}  (a line that Korvin cannot read)")
            continue
        time = str(entry.get("time")).replace("T", " ").rstrip("Z")
        rows.append(f"{entry['seq']:>6}  {time:19}  {str(entry.get('event')):17} {describe(entry)}")
    return clean("\n".join(rows)) + "\nThis list does not check the seals. Type python -m korvin check for that.\n"


def describe(entry: dict) -> str:
    """Return the details of an entry in one line. A tool call looks like its action line in the chat."""
    if entry.get("event") == "tool call":
        shown = "" if entry.get("argument") is None else f' "{entry["argument"]}"'
        return f"{entry.get('tool')}{shown} -> {entry.get('outcome')} ({entry.get('decision')})"
    return "; ".join(f"{key}: {value}" for key, value in entry.items() if key not in FIXED)
