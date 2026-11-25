"""Start Korvin from the command line with: python -m korvin

This file turns on the network guard first. Then it runs the command that the user typed.
The commands are the chat (the default), the guided setup, the sealed log, and the tool servers.
When no settings file exists yet, Korvin starts the guided setup before the chat.
"""

import argparse
import sys

from korvin import __version__, guard, seal, servers
from korvin.chat import run_chat, write_stdout
from korvin.config import SETTINGS_NAME, ConfigError, find_settings_file, load_settings, user_data_dir
from korvin.door import DoorError, ModelDoor
from korvin.first_run import run_setup

LOG_ROWS = 20  # how many entries "python -m korvin log" shows when the user does not say


def main(argv: list[str] | None = None) -> int:
    """Run Korvin and return the exit code."""
    guard.install()
    use_utf8_output()
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["server"]:
            return servers.command(argv[1:], input, write_stdout)
        args = parse_args(argv)
        if args.command in ("check", "log"):
            return show_log(args)
        settings_file = find_settings_file(args.config)
        if args.command == "setup" or settings_file is None:
            # Korvin writes no file of its own before the setup has finished.
            door = ModelDoor(load_settings(args.config).provider)
            if not run_setup(door, str(settings_file or user_data_dir() / SETTINGS_NAME)):
                return 2
            if args.command == "setup":
                return 0
        settings = load_settings(args.config, args.model, args.folder)
        door = ModelDoor(settings.provider)
        if settings.model is None:
            return show_models(door)
    except (ConfigError, DoorError) as error:
        print(error, file=sys.stderr)
        return 2
    return run_chat(settings, door)


def use_utf8_output() -> None:
    """Make printed text UTF-8 on Windows, where an old code page cannot show every character."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Read the command and the command-line options."""
    parser = argparse.ArgumentParser(prog="korvin", description="Korvin: a small, private AI assistant.")
    parser.add_argument(
        "command", nargs="?", choices=("setup", "check", "log", "server"),
        help="setup: run the guided setup again; check: check the sealed log; log: show its last entries; "
        "server: add, list, or remove a tool server (python -m korvin server --help)",
    )
    parser.add_argument("--config", metavar="PATH", help="read the settings from this JSON file")
    parser.add_argument("--model", metavar="NAME", help="use this model instead of the one in the settings")
    parser.add_argument("--folder", metavar="PATH", help="let Korvin read the files in this folder")
    parser.add_argument("--last", metavar="N", type=int, default=LOG_ROWS, help="log: how many entries to show")
    parser.add_argument("--seal", metavar="VALUE", help="check: also look for this seal, which you kept elsewhere")
    parser.add_argument("--version", action="version", version=f"Korvin {__version__}")
    return parser.parse_args(argv)


def show_log(args: argparse.Namespace) -> int:
    """Check the sealed log, or show its last entries. Return 0 if all is well, or 1."""
    path = load_settings(args.config).log_file
    if args.command == "log":
        print(seal.table(path, args.last), end="")
        return 0
    intact, report = seal.check(path, args.seal)
    print(report, end="")
    return 0 if intact else 1


def show_models(door: ModelDoor) -> int:
    """Tell the user how to choose a model. Return exit code 2."""
    names = door.list_models()
    print("No model is chosen.")
    if not names:
        print("No models are installed. Download one with: ollama pull <model-name>")
        return 2
    print("Installed models:")
    for name in names:
        print(f"  {name}")
    print('Choose one with --model NAME, set "model" in the settings file, or type: python -m korvin setup')
    return 2


if __name__ == "__main__":
    sys.exit(main())
