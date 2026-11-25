"""Add, approve, and use local tool servers: in the chat, and with the "server" commands in the terminal.

Korvin shows each tool as the model will see it, and stores a SHA-256 fingerprint of each tool that the user approves.
At each start, a changed or new tool stays hidden from the model until the user approves it.
Korvin controls which tools the model may call. It cannot control what a server does inside.
"""

import argparse
import hashlib
import json
import re

from korvin import config, mcp, tools
from korvin.config import Settings
from korvin.gate import Gate, Reader, Writer, clean, defuse, said_yes
from korvin.seal import Log

SERVER_TOOL_LIMIT = 8  # the most server tools that the model sees, from all servers together
DESCRIPTION_LIMIT = 300  # the longest tool description, in characters, that the model sees
SCHEMA_LIMIT = 2_000  # the longest input schema, in characters of JSON. Korvin refuses a tool with a longer one.
SCHEMA_DEPTH = 20  # the deepest nesting that Korvin accepts in an input schema
ARGUMENT_LIMIT = 2_000  # the longest arguments, in characters of JSON, that Korvin sends to a server tool
TOOL_NAME = r"[A-Za-z0-9_-]{1,48}"  # the tool names that Korvin accepts from a server
USAGE = (
    "  python -m korvin server add NAME --risk read|write [--env VARIABLE] -- COMMAND ARGUMENTS...\n"
    "  python -m korvin server list\n  python -m korvin server remove NAME\n"
)
CONTROL = "Korvin 1.0 refuses servers that control other programs. A small model is too easy to trick.\n"
WAITING = "These tools of {server} need your approval. A server can hide orders in a description, so read each one.\n"
APPROVE = "Approve these tools?  [y] yes   [n] no  (Enter = no)\n"
QUESTION = 'Korvin wants to use the tool "{tool}" of the tool server "{server}" (risk: {risk}) with these arguments:'


class Servers:
    """The tool servers of one chat: the running servers, and the approved tools that the model may call."""

    def __init__(self) -> None:
        self.running: dict[str, mcp.Server] = {}
        self.offered: dict[str, tuple[str, str, str]] = {}  # the model's tool name -> (server, tool, risk)
        self.schemas: list[dict] = []  # the offered tools, as the model sees them

    def start(self, settings: Settings, read_line: Reader, write: Writer, log: Log) -> None:
        """Start each server in the settings. Offer the model only the approved tools that did not change."""
        stored = dict(settings.servers)
        for name, entry in settings.servers.items():
            try:
                self.running[name], found = connect(name, entry, log)
            except (mcp.ServerError, KeyboardInterrupt) as error:  # Ctrl+C skips a slow server
                write(clean(f"\nThe tool server {name} did not start: {error or 'you pressed Ctrl+C'}\n"))
                log.add("server failed", server=name, error=str(error)[:120])
                continue
            stored[name] = {**entry, "approved": review(name, entry["approved"], found, read_line, write, log)}
            for tool in [tool for tool in found if not problem(name, tool)]:
                model_name, kept = f"{name}_{tool['name']}", stored[name]["approved"].get(tool["name"], {})
                if kept.get("sha256") != record(tool)["sha256"] or model_name in self.offered:
                    continue  # an unapproved or changed tool never reaches the model
                if len(self.offered) >= SERVER_TOOL_LIMIT:
                    write(clean(f"The model sees at most {SERVER_TOOL_LIMIT} server tools, so not {model_name}.\n"))
                    continue
                self.offered[model_name] = (name, tool["name"], entry["risk"])
                self.schemas.append(model_schema(model_name, tool))
        if stored != settings.servers and settings.source:
            config.write_settings(settings.source, servers=stored)
        if self.running:
            write(clean(f"Server tools for the model: {', '.join(self.offered) or 'none'}. Korvin asks before each "
                        "call.\nA tool server is a separate program. Korvin cannot see what it does inside.\n"))

    def run(self, gate: Gate, name: str, text: str) -> tuple[str | None, tools.Result | None, str]:
        """Check the arguments, ask the user, and call the tool. Return the arguments, the result, and the decision.

        The question shows the exact arguments in full. The result is None after a "no". A result is outside text,
        so Korvin cleans it, defuses it, and cuts it.
        """
        server, tool, risk = self.offered[name]
        try:
            arguments = json.loads(text or "{}")
        except json.JSONDecodeError:
            arguments = None
        if not isinstance(arguments, dict) or len(text) > ARGUMENT_LIMIT:
            refusal = tools.Result(f"Wrong arguments. Send one JSON object of at most {ARGUMENT_LIMIT:,} characters.",
                                   "error: wrong arguments")
            return None, refusal, "refused: wrong arguments, so Korvin did not ask"
        shown_arguments = json.dumps(arguments, ensure_ascii=False)
        question = QUESTION.format(tool=tool, server=server, risk=risk)
        if not gate.allows(name, json.dumps(arguments, ensure_ascii=False, indent=2), question=question):
            return shown_arguments, None, gate.decision
        try:
            text, failed = self.running[server].call(tool, arguments)
        except mcp.ServerError as error:
            failure = tools.Result(f"The tool did not work. {error}", f"error: {str(error).rstrip('.')}")
            return shown_arguments, failure, gate.decision
        text = defuse(clean(text)) or "The tool returned no text."
        summary = "error: the tool failed" if failed else tools.count(len(text), "character", "characters")
        text = ("The tool server reported an error:\n" if failed else "") + text
        return shown_arguments, tools.cap(tools.Result(text, summary, outside=True)), gate.decision

    def close(self) -> None:
        """Stop every server of this chat."""
        for server in self.running.values():
            server.close()


def connect(name: str, entry: dict, log: Log) -> tuple[mcp.Server, list[dict]]:
    """Start one server and return it with its tools. If that fails, stop the server and raise the error again."""
    server = mcp.Server(entry["command"], config.child_environment(entry["env"]))
    try:
        server.start()
        found = server.tools()
    except (mcp.ServerError, KeyboardInterrupt):
        server.close()
        raise
    log.add("server start", server=name, protocol=server.version, tools=len(found))
    return server, found


def record(tool: dict) -> dict:
    """Return what Korvin stores of an approved tool: the fingerprint of its name, description, and input schema."""
    description, schema = tool.get("description"), tool["inputSchema"]
    text = json.dumps({"name": tool["name"], "description": description, "input_schema": schema}, sort_keys=True)
    sha256 = hashlib.sha256(text.encode("ascii")).hexdigest()
    return {"sha256": sha256, "description": description, "input_schema": schema}


def problem(server: str, tool: dict) -> str:
    """Return why Korvin cannot offer this tool to the model, or "" if it can."""
    name, schema = tool.get("name"), tool.get("inputSchema")
    if not isinstance(name, str) or not re.fullmatch(TOOL_NAME, name):
        return "its name is not 1 to 48 letters, digits, _ or -"
    if f"{server}_{name}" in tools.TOOLS:
        return "its name would be the same as a built-in tool"
    if not isinstance(tool.get("description", ""), str):
        return "its description is not text"
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return "its input schema is not a JSON schema of an object"
    waiting = [(schema, 1)]
    while waiting:
        value, depth = waiting.pop()
        if depth > SCHEMA_DEPTH:
            return f"its input schema is nested deeper than {SCHEMA_DEPTH} levels"
        if isinstance(value, dict) and isinstance(value.get("$ref"), str) and not value["$ref"].startswith("#"):
            return "its input schema needs a $ref outside itself, such as a web address"
        items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        waiting += [(item, depth + 1) for item in items]
    if len(json.dumps(schema)) > SCHEMA_LIMIT:
        return f"its input schema is longer than {SCHEMA_LIMIT:,} characters"
    return ""


def model_schema(name: str, tool: dict) -> dict:
    """Return the tool as the model sees it. A description is outside text, so Korvin cleans, defuses, and cuts it."""
    description = defused(tool.get("description") or "")
    if len(description) > DESCRIPTION_LIMIT:
        description = description[: DESCRIPTION_LIMIT - 3] + "..."
    parameters = defused(tool["inputSchema"])
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


def defused(value: object) -> object:
    """Return a copy of a value from a server with each text cleaned and defused, keys included."""
    if isinstance(value, str):
        return defuse(clean(value))
    if isinstance(value, list):
        return [defused(item) for item in value]
    if isinstance(value, dict):
        return {defused(key): defused(item) for key, item in value.items()}
    return value


def review(server: str, approved: dict, found: list[dict], read_line: Reader, write: Writer, log: Log) -> dict:
    """Ask the user about the new and changed tools. Return the approved fingerprints, with any new approval."""
    waiting = []
    for tool in found:
        why = problem(server, tool)
        if why:
            write(clean(f"Korvin refuses the tool {str(tool.get('name'))[:48]} of the server {server}: {why}.\n"))
            log.add("tool refused", server=server, tool=str(tool.get("name"))[:48], reason=why)
            continue
        old, new = approved.get(tool["name"]), record(tool)
        if old is None or old["sha256"] != new["sha256"]:
            what = [k.replace("_", " ") for k in ("description", "input_schema") if old and old.get(k) != new[k]]
            change = "NEW" if old is None else f"CHANGED: its {' and '.join(what) or 'fingerprint'} changed"
            log.add("tool new" if old is None else "tool changed", server=server, tool=tool["name"], change=change)
            waiting.append((tool, new, change, old))
    if not waiting:
        return approved
    write(clean(WAITING.format(server=server)) + "".join(shown(server, *item) for item in waiting) + APPROVE)
    yes = said_yes(read_line, write, "approve> ")
    names = ", ".join(tool["name"] for tool, *_rest in waiting)
    log.add("tools approved" if yes else "tools declined", server=server, tools=names)
    return {**approved, **{tool["name"]: new for tool, new, _change, _old in waiting}} if yes else approved


def shown(server: str, tool: dict, _new: dict, change: str, old: dict | None) -> str:
    """Return one tool in the approval list: what changed, and what the model will see."""
    seen = model_schema(f"{server}_{tool['name']}", tool)["function"]
    lines = [f"  - {tool['name']}  ({change})", f"    Description: {seen['description'] or '(none)'}",
             f"    Input: {json.dumps(seen['parameters'], ensure_ascii=False)}"]
    if old:
        lines += [f"    Description before: {defused(old.get('description') or '(none)')[:DESCRIPTION_LIMIT]}",
                  f"    Input before: {json.dumps(defused(old.get('input_schema')), ensure_ascii=False)}"]
    return clean("\n".join(lines)) + "\n"


def command(argv: list[str], read_line: Reader, write: Writer) -> int:
    """Run "server add", "server list", or "server remove". Return the exit code."""
    split = argv.index("--") if "--" in argv else len(argv)
    parser = argparse.ArgumentParser(prog="python -m korvin server", usage="\n" + USAGE)
    parser.add_argument("action", choices=("add", "list", "remove"))
    parser.add_argument("name", nargs="?", default="")
    parser.add_argument("--risk", choices=("read", "write", "control"), help="what the server's tools can do")
    parser.add_argument("--env", action="append", default=[], metavar="VARIABLE", help="pass this variable on")
    parser.add_argument("--config", metavar="PATH", help="read the settings from this JSON file")
    args, program = parser.parse_args(argv[:split]), argv[split + 1 :]
    if config.find_settings_file(args.config) is None:
        write("Korvin has no settings yet. Type python -m korvin setup first.\n")
        return 2
    settings = config.load_settings(args.config)
    log = Log(settings.log_file, write)
    if args.action == "list":
        write(listing(settings))
        return 0
    if args.action == "add":
        return add(settings, args, program, read_line, write, log)
    if args.name not in settings.servers:
        write(clean(f"There is no tool server named {args.name}. Type python -m korvin server list to see them.\n"))
        return 2
    config.write_settings(settings.source, servers={k: v for k, v in settings.servers.items() if k != args.name})
    log.add("server removed", server=args.name)
    write(f"Removed the tool server {args.name}.\n")
    return 0


def add(settings: Settings, args: argparse.Namespace, program: list[str], read_line: Reader, write: Writer,
        log: Log) -> int:
    """Start a new server, show its tools, and store it with the tools that the user approved."""
    name, entry = args.name, {"command": program, "risk": args.risk, "env": args.env, "approved": {}}
    for refused, message in [
        (not re.fullmatch(config.SERVER_NAME, name), "A server name has 1 to 16 small letters and digits: clock.\n"),
        (name in settings.servers, f"A tool server named {name} exists already. To replace it, remove it first.\n"),
        (args.risk == "control", CONTROL),
        (args.risk is None or not program, "Give a risk level, and the server's command after --:\n" + USAGE),
    ]:
        if refused:
            write(message)
            return 2
    try:
        server, found = connect(name, entry, log)
    except mcp.ServerError as error:
        write(clean(f"Korvin could not use the server: {error}\n"))
        return 1
    server.close()
    entry["approved"] = review(name, {}, found, read_line, write, log)
    if not entry["approved"]:
        write("You approved no tool, so Korvin did not add the server.\n")
        return 1
    config.write_settings(settings.source, servers={**settings.servers, name: entry})
    log.add("server added", server=name, risk=args.risk, program=program[0][:120])
    write(clean(f"Added the tool server {name}. The next chat can use its approved tools.\n"))
    return 0


def listing(settings: Settings) -> str:
    """Return the tool servers in the settings, with their risk levels, approved tools, and commands."""
    if not settings.servers:
        return "No tool servers yet. Add one with:\n" + USAGE
    rows = [f"Tool servers in {settings.source}:"]
    for name, entry in settings.servers.items():
        rows += [f"  {name}  (risk: {entry['risk']})  approved tools: {', '.join(entry['approved']) or 'none'}",
                 f"      command: {' '.join(entry['command'])}    variables: {', '.join(entry['env']) or 'none'}"]
    return clean("\n".join(rows)) + "\n"
