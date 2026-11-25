"""The four built-in tools: list a folder, read a file, save a note, and find notes.

Each tool has a schema that tells the model how to call it, next to the code that runs it.
The two file tools work only inside the folder that the user chose.
Each result is plain text for the model, with a short summary for the user.
"""

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from korvin.config import Settings, is_network_path

LIST_LIMIT = 200  # the most names that list_folder returns
READ_LIMIT = 200_000  # the largest file, in bytes, that read_file reads
NOTE_LIMIT = 2_000  # the longest note, in characters
FIND_LIMIT = 10  # the most notes that find_note returns
RESULT_LIMIT = 20_000  # the longest result, in characters, that the model gets

NO_FOLDER = "No folder is chosen, so the file tools are off. The user can choose one: start Korvin with --folder PATH."
# The model-facing texts tell a small model how to recover. They never show the real path of the chosen folder.
OUTSIDE = (
    "Refused: the path is outside the chosen folder. All paths are relative to the chosen folder. "
    'To list the chosen folder, use list_folder with ".".'
)
SEE_NAMES = 'Use list_folder with "." to see the real names.'
# Windows names for devices, not files. Korvin refuses them on every system, so the rule is the same everywhere.
DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
DEVICE_NAMES |= {port + digit for port in ("COM", "LPT") for digit in "123456789\u00b9\u00b2\u00b3"}


class ToolError(Exception):
    """Korvin refused a tool call, or the tool failed. The message tells the model what happened."""

    def __init__(self, summary: str, message: str) -> None:
        super().__init__(message)
        self.summary = summary  # the few words that the user sees


@dataclass(frozen=True)
class Result:
    """The result of one tool call: the text for the model, and a short summary for the user."""
    text: str
    summary: str
    outside: bool = False  # the text holds the contents of a file or a note, so it can hold hidden orders


def schema(name: str, description: str, argument: str, about: str) -> dict:
    """Return an OpenAI-style function schema for a tool that takes one text argument."""
    properties = {argument: {"type": "string", "description": about}}
    parameters = {"type": "object", "properties": properties, "required": [argument], "additionalProperties": False}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


def count(number: int, one: str, many: str) -> str:
    """Return a number with the right word, such as "1 note" or "1,204 characters"."""
    return f"{number:,} {one if number == 1 else many}"


def inside_folder(settings: Settings, raw: str) -> Path:
    """Turn a path from the model into a real path, and prove that it is inside the chosen folder.

    Relative paths start at the chosen folder. Absolute paths must point inside it.
    An empty path means the chosen folder itself, the same as ".". Small models often send one.
    The proof follows links, junctions, and ".." first. Then it compares whole path parts, not text.
    The text checks come first, so Korvin never touches a network path, a device, or another drive.
    """
    folder = settings.folder
    if folder is None:
        raise ToolError("refused: no folder chosen (start Korvin with --folder PATH)", NO_FOLDER)
    if not raw.strip():
        raw = "."
    real = None
    candidate = folder / raw  # an absolute path replaces the folder here
    # A path on another drive is outside. Korvin checks this first, so it never touches that drive.
    if is_plain_path(raw) and candidate.drive.casefold() == folder.drive.casefold():
        try:
            real = Path(os.path.realpath(candidate))
        except (OSError, ValueError):
            pass
    if real is None or (real != folder and folder not in real.parents):
        raise ToolError("refused: outside the chosen folder", OUTSIDE)
    return real


def is_plain_path(raw: str) -> bool:
    """Return False for text that is not a plain file path, such as a network path or a device name."""
    # Two slashes at the start also name a device path (\\.\ and \\?\), not only a network path.
    if not raw.strip() or "\0" in raw or is_network_path(raw):
        return False
    # A colon is allowed only after a drive letter at the start, as in C:\. Any other colon can name
    # an alternate data stream (file.txt:secret) or a path that depends on another drive (D:file.txt).
    rest = raw[2:] if re.match(r"[A-Za-z]:[\\/]", raw) else raw
    if ":" in rest:
        return False
    return not any(part.split(".")[0].rstrip(" ").upper() in DEVICE_NAMES for part in re.split(r"[\\/]", raw))


LIST_FOLDER = schema(
    "list_folder", 'List the files and folders in the chosen folder. Use "." for the chosen folder itself.',
    "path", 'A path relative to the chosen folder, such as ".".',
)


def list_folder(settings: Settings, path: str) -> Result:
    """Return the sorted names in a folder. Folder names end with "/"."""
    folder = inside_folder(settings, path)
    if not folder.is_dir():
        raise ToolError("error: not a folder", f'"{path}" is not a folder, or it does not exist. {SEE_NAMES}')
    with os.scandir(folder) as entries:
        names = [entry.name + ("/" if entry.is_dir() else "") for entry in entries]
    names.sort(key=lambda name: (name.casefold(), name))
    lines = [f"{count(len(names), 'entry', 'entries')}. Folder names end with /."] + names[:LIST_LIMIT]
    if len(names) > LIST_LIMIT:
        lines.append(f"... and {len(names) - LIST_LIMIT:,} more.")
    return Result("\n".join(lines), count(len(names), "entry", "entries"))


READ_FILE = schema(
    "read_file", "Read a text file in the chosen folder.",
    "path", "A file path relative to the chosen folder, as list_folder shows it.",
)


def read_file(settings: Settings, path: str) -> Result:
    """Return the text of a file. Refuse a file that is too large or that is not UTF-8 text."""
    real = inside_folder(settings, path)
    if not real.is_file():
        raise ToolError("error: no such file", f'"{path}" does not exist or is not a file. {SEE_NAMES}')
    with open(real, "rb") as file:
        # Read one byte more than the limit, so a file that grew after a size check is still refused.
        data = file.read(READ_LIMIT + 1)
    if len(data) > READ_LIMIT:
        message = f"The file is larger than {READ_LIMIT:,} bytes. Korvin does not read files that large."
        raise ToolError("refused: file too large", message)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = "\0"
    # A NUL character is valid UTF-8, but it does not belong in a text file.
    if "\0" in text:
        raise ToolError("refused: not UTF-8 text", "The file is not UTF-8 text. Korvin reads only UTF-8 text files.")
    return Result(text or "The file is empty.", count(len(text), "character", "characters"), outside=True)


SAVE_NOTE = schema(
    "save_note", "Save a short note for the user. Use it only when the user asks you to save a note.",
    "text", f"The text of the note, at most {NOTE_LIMIT:,} characters.",
)


def check_note(text: str) -> None:
    """Refuse an empty note or a note that is too long, before Korvin asks the user about it."""
    if not text.strip():
        raise ToolError("error: empty note", "The note is empty. Send the text of the note.")
    if len(text) > NOTE_LIMIT:
        message = f"The note has {len(text):,} characters. A note can have at most {NOTE_LIMIT:,}."
        raise ToolError("error: note too long", message)


def save_note(settings: Settings, text: str) -> Result:
    """Add one note, with the date and time, to the end of the notes file."""
    note = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "text": text}
    # Korvin creates the notes file and its folder only now, after the user approved the note.
    settings.notes_file.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.notes_file, "a", encoding="utf-8", newline="\n") as file:
        # json.dumps keeps each note on one line, and its ASCII form can store any text the model sends.
        file.write(json.dumps(note) + "\n")
    return Result("Saved the note.", "saved")


FIND_NOTE = schema(
    "find_note", "Find the user's saved notes that contain every word of a search. Notes are not files.",
    "query", "The words to search for. Use an empty text to get the newest notes.",
)


def find_note(settings: Settings, query: str) -> Result:
    """Return the newest notes that contain every word of the query, in any case."""
    if not settings.notes_file.exists():
        return Result("No notes yet.", "no notes yet")
    words = query.casefold().split()
    notes = [note for note in read_notes(settings.notes_file) if all(word in note["text"].casefold() for word in words)]
    found = notes[::-1][:FIND_LIMIT]
    if not found:
        return Result("No notes match the search.", "no matching notes")
    text = "\n".join(f"- {note['time']}: {note['text']}" for note in found)
    return Result(text, count(len(found), "note", "notes"), outside=True)


def read_notes(path: Path) -> list[dict]:
    """Return the notes in the notes file, oldest first. Skip any line that is not a note."""
    notes = []
    with open(path, encoding="utf-8", errors="replace") as file:
        for line in file:
            try:
                note = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(note, dict) and isinstance(note.get("time"), str) and isinstance(note.get("text"), str):
                notes.append(note)
    return notes


@dataclass(frozen=True)
class Tool:
    """One built-in tool: its schema, the name of its one text argument, and the function that runs it."""
    schema: dict
    argument: str
    run: Callable[[Settings, str], Result]


TOOLS = {
    "list_folder": Tool(LIST_FOLDER, "path", list_folder),
    "read_file": Tool(READ_FILE, "path", read_file),
    "save_note": Tool(SAVE_NOTE, "text", save_note),
    "find_note": Tool(FIND_NOTE, "query", find_note),
}
SCHEMAS = [tool.schema for tool in TOOLS.values()]


def unknown_tool(name: str) -> ToolError:
    """Return the refusal for a tool name that Korvin does not know."""
    return ToolError("refused: unknown tool", f'Korvin has no tool named "{name}". Use only the tools in the list.')


def find_tool(name: str) -> Tool:
    """Return the built-in tool with this name, or refuse the name."""
    if name not in TOOLS:
        raise unknown_tool(name)
    return TOOLS[name]


def argument(name: str, arguments: object) -> str:
    """Check the arguments of one tool call. Return the value of the tool's one argument.

    The message names the expected argument, so that a small model can correct its call.
    """
    key = find_tool(name).argument
    if not isinstance(arguments, dict) or set(arguments) != {key} or not isinstance(arguments[key], str):
        message = f'Wrong arguments for {name}. Send exactly this JSON object: {{"{key}": "<text>"}}.'
        raise ToolError("error: wrong arguments", message)
    if name == "save_note":
        check_note(arguments[key])
    return arguments[key]


def run(settings: Settings, name: str, value: str) -> Result:
    """Run one tool with a checked argument, and return its result. A failure becomes a result, too."""
    try:
        result = find_tool(name).run(settings, value)
    except ToolError as error:
        return Result(str(error), error.summary)
    except OSError as error:
        reason = error.strerror or "the file system refused the action"
        return Result(f"The tool failed: {reason}.", f"error: {reason}")
    return cap(result)


def cap(result: Result) -> Result:
    """Cut a result that is longer than RESULT_LIMIT, and say so in the result."""
    if len(result.text) <= RESULT_LIMIT:
        return result
    note = f"\n[Korvin cut this result here. The full result has {len(result.text):,} characters.]"
    text = result.text[: RESULT_LIMIT - len(note)] + note
    return replace(result, text=text, summary=f"{result.summary}, cut to {RESULT_LIMIT:,}")
