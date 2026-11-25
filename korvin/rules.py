"""Keep the user's standing rules, such as "answer in Spanish", and add them to every request.

Only the user creates a rule: with /rule, or with a "yes" when Korvin asks about a message that sounds like one.
Nothing from a file, a note, or the model can create a rule.
The rules stay in memory until Korvin ends, and /new keeps them.
Korvin never stores them in the conversation. It adds them to each request in two places:
the system message, and a short reminder after the user's latest message. A small model forgets old rules.
"""

import re

RULE_LIMIT = 5  # the most standing rules at a time
RULE_CHARS = 200  # the longest standing rule, in characters
# A sentence with one of these phrases sounds like a standing rule, in English or in Spanish.
RULE_PHRASES = (
    r"(?i)from now on|for the rest of (this|the) conversation|in every (answer|reply|response)"
    r"|^\W*(please,? )?always\b|a partir de ahora|en cada respuesta|^\W*(por favor,? )?siempre\b"
)
SYSTEM_PART = "\n\nThe user's standing rules. Follow each one in every answer:\n"
REMINDER = "\n\n(Follow my standing rules in this answer too: {rules})"
USAGE = "Type /rule TEXT to add a standing rule, /rules to see them, or /rule clear to remove them.\n"


def sounds_like_rule(text: str) -> str:
    """Return the sentences of a message that sound like a standing rule, or "" if none does."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentence for sentence in sentences if re.search(RULE_PHRASES, sentence))


def add(rules: list[str], text: str) -> str:
    """Add a standing rule, if it fits the limits. Return the message for the user."""
    if len(rules) >= RULE_LIMIT:
        return f"Korvin keeps at most {RULE_LIMIT} standing rules. Type /rule clear to remove them.\n"
    if len(text) > RULE_CHARS:
        return f"A standing rule can have at most {RULE_CHARS} characters. This one has {len(text)}.\n"
    rules.append(text)
    return "Korvin will send this rule with every request until it ends. /new keeps it.\n"


def command(rules: list[str], line: str) -> str:
    """Run /rules, /rule clear, or /rule TEXT. Return the message for the user."""
    name, _space, text = line.partition(" ")
    text = text.strip()
    if name == "/rules" and not text:
        listed = "".join(f"  {number}. {rule}\n" for number, rule in enumerate(rules, 1))
        return f"Standing rules:\n{listed}" if rules else "No standing rules. " + USAGE
    if name == "/rule" and text == "clear":
        rules.clear()
        return "Removed all standing rules.\n"
    if name == "/rule" and text:
        return add(rules, text)
    return USAGE


def with_rules(messages: list[dict], rules: list[str]) -> list[dict]:
    """Return a request: the messages, with the rules added to the system message and to the latest user message.

    The stored conversation does not change.
    """
    if not rules:
        return messages
    request = [{**messages[0], "content": messages[0]["content"] + SYSTEM_PART + "\n".join(f"- {r}" for r in rules)}]
    request += messages[1:]
    last = max(index for index, message in enumerate(request) if message["role"] == "user")
    reminder = REMINDER.format(rules=" ".join(rules))
    request[last] = {**request[last], "content": request[last]["content"] + reminder}
    return request
