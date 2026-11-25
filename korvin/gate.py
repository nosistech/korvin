"""Decide whether a tool may run, and ask the user when the rules say so.

The rules: the reading tools run without a question, saving a note needs a "yes",
and a tool that Korvin does not know never runs.
A "yes, for this session" answer lasts until Korvin ends.
One more rule guards against hidden orders. Once a file or a note entered the current request,
reading a file that the user did not name needs a "yes".
Every tool from a tool server needs a "yes". After outside text entered the request, even a session "yes" asks again.
This file also makes control characters visible, so that text from the model cannot hide or fake what the user sees.
It also breaks chat-format markers in tool results, so that the model service reads them as plain text.
"""

import re
import unicodedata
from collections.abc import Callable

Reader = Callable[[str], str]  # reads one line that the user types, after a prompt
Writer = Callable[[str], None]  # shows text to the user
ALLOW, ASK, DENY = "allow", "ask", "deny"
# The rule for each built-in tool. Any other tool name gets DENY.
POLICY = {"list_folder": ALLOW, "read_file": ALLOW, "find_note": ALLOW, "save_note": ASK}
QUESTIONS = {"save_note": "Korvin wants to save this note:"}
OPTIONS = "Allow?  [y] yes, once   [s] yes, for this session   [n] no  (Enter = no)"
READ_QUESTION = (
    "A file or note that Korvin just read may have asked for this. Korvin wants to read a file that you did not name:"
)
READ_OPTIONS = "Allow?  [y] yes, once   [s] yes, all reads for this request   [n] no  (Enter = no)"
OUTSIDE_WARNING = "A file, note, or tool result entered this request. It may hold an order that asked for this call.\n"
ONCE, SESSION = "once", "session"
# Every other answer, an empty one included, means no.
ANSWERS = {"y": ONCE, "yes": ONCE, "s": SESSION, "session": SESSION}
# How the sealed log names each answer to a question.
DECISIONS = {ONCE: "user said yes once", SESSION: "user said yes for the session", None: "user said no"}
# Characters that change the direction of text. They can make text look different from what it is.
DIRECTION_MARKS = {chr(code) for code in [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]}
# Chat-format markers, such as <|im_end|>, the Qwen tags for tool calls and thinking, and Qwen's [PAD0] to [PAD249].
# The model service turns them into control tokens, so a file could fake the end of a message.
QWEN_TAGS = r"<(/?(?:tool_call|tool_response|think))>|\[(PAD\d+)\]"


def rule(name: str) -> str:
    """Return ALLOW, ASK, or DENY for a tool name."""
    return POLICY.get(name, DENY)


class Gate:
    """Ask the user before a tool runs, when the rules say so. Remember the "yes, for this session" answers."""

    def __init__(self, read_line: Reader, write: Writer) -> None:
        self.read_line = read_line
        self.write = write
        self.session_grants: set[str] = set()  # tool names that the user allowed until Korvin ends
        self.outside_text = False  # a file or a note entered the current request
        self.reads_granted = False  # the user allowed every read until the current request ends
        self.decision = ""  # why the last call of allows() gave its answer, in words for the sealed log

    def new_request(self) -> None:
        """Forget what happened in the last request. Call this for each new message from the user."""
        self.outside_text = self.reads_granted = False

    def allows(self, name: str, detail: str, said: str = "", question: str = "") -> bool:
        """Return True if the tool may run. Ask the user first if the rules say so.

        The detail is what the tool will use, such as the text of a note. The question shows it in full.
        "said" is everything that the user typed in this conversation. It decides if the user named a file.
        A question is given only for a tool from a tool server. Such a tool always needs a "yes".
        """
        if name == "read_file" and self.outside_text and not named(detail, said):
            if self.reads_granted:
                self.decision = "user said yes for this request earlier"
                return True
            answer = self.ask(READ_QUESTION, detail, READ_OPTIONS)
            self.reads_granted = answer == SESSION
            self.decision = "user said yes for this request" if answer == SESSION else DECISIONS[answer]
            return answer in (ONCE, SESSION)
        decision = ASK if question else rule(name)
        if decision != ASK:
            self.decision = "allowed by rule" if decision == ALLOW else "denied by rule"
            return decision == ALLOW
        warned = bool(question) and self.outside_text
        if name in self.session_grants and not warned:
            self.decision = "user said yes for the session earlier"
            return True
        question = question or QUESTIONS.get(name, f"Korvin wants to use the tool {name} with:")
        answer = self.ask((OUTSIDE_WARNING if warned else "") + question, detail, OPTIONS)
        self.decision = DECISIONS[answer] + (", after outside text" if warned else "")
        if answer == SESSION:
            self.session_grants.add(name)
        return answer in (ONCE, SESSION)

    def ask(self, question: str, detail: str, options: str) -> str | None:
        """Show the question and the detail, and return ONCE, SESSION, or None for no."""
        # Indent the detail, so that the user can see where it starts and ends.
        shown = "\n".join("    " + line for line in clean(detail).split("\n"))
        self.write(f"{clean(question)}\n{shown}\n{options}\n")
        try:
            return ANSWERS.get(self.read_line("allow> ").strip().lower())
        except (EOFError, KeyboardInterrupt):
            self.write("\n")
            return None


def said_yes(read_line: Reader, write: Writer, prompt: str) -> bool:
    """Read the answer to a yes-or-no question. Return True only for "y" or "yes". Ctrl+C or no input means no."""
    try:
        return read_line(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        write("\n")
        return False


def file_name(path: str) -> str:
    """Return the name of the file that a path points to, after "." and ".." are applied, as Windows does."""
    parts: list[str] = []
    for part in re.split(r"[\\/]", path):
        if part == "..":
            parts = parts[:-1]
        elif part not in ("", "."):
            parts.append(part)
    return parts[-1] if parts else ""


def named(path: str, said: str) -> bool:
    """Return True if the user typed the file's name, in any case, as a whole word."""
    name = file_name(path)
    return bool(name) and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", said, re.IGNORECASE) is not None


def defuse(text: str) -> str:
    """Break chat-format markers in a tool result, so that they stay plain text. The text stays readable.

    "<|" becomes "‹|" and "|>" becomes "|›", which breaks every marker of the form <|...|>.
    The Qwen tags become ‹tool_call›, ‹/think›, ‹PAD7›, and so on.
    """
    return re.sub(QWEN_TAGS, r"‹\1\2›", text.replace("<|", "‹|").replace("|>", "|›"))


def clean(text: str) -> str:
    """Make control characters visible, such as ESC as \\x1b. Keep newlines and tabs.

    A control character can move the cursor, change colors, or erase text in a terminal.
    """
    return "".join(visible(char) for char in text.replace("\r\n", "\n"))


def visible(char: str) -> str:
    """Return the character, or a visible escape for a control character or a direction mark."""
    if char in "\n\t":
        return char
    # "Cc" is a control character. "Cs" is half of a broken character pair, which some terminals cannot print.
    if unicodedata.category(char) in ("Cc", "Cs") or char in DIRECTION_MARKS:
        return char.encode("unicode_escape").decode("ascii")
    return char
