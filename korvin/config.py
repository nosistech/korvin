"""Load and check Korvin's settings.

The settings come from a JSON file, or from built-in defaults. The guided setup writes that file.
Anything unknown or invalid stops Korvin with a clear message.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from korvin import guard

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
LOCAL = {"local": {"base_url": DEFAULT_BASE_URL, "remote": False}}
DATA_FILES = {"notes_file": "notes.jsonl", "log_file": "log.jsonl"}  # each file's name in Korvin's data folder
DEFAULTS = {"model": None, "provider": "local", "providers": LOCAL, "folder": None, "servers": {}}
DEFAULTS |= dict.fromkeys(DATA_FILES)
TOP_KEYS = set(DEFAULTS)
PROVIDER_KEYS = {"base_url", "remote"}
SETTINGS_NAME = "settings.json"  # the settings file that the guided setup writes in Korvin's data folder
CONTEXT_GOAL = 65_536  # Korvin is built for a model that holds this many tokens
SERVER_KEYS = {"command", "risk", "env", "approved"}  # the keys of one tool server in the settings
SERVER_NAME = r"[a-z][a-z0-9]{0,15}"  # no "_", so the model's name "server_tool" always shows where the server ends
RISKS = ("read", "write")  # a third level, "control", is refused in version 1.0 (D-010)
# The variables that most programs need to start. A tool server gets only these, and the ones that the user named.
CHILD_VARIABLES = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE",
                   "APPDATA", "LOCALAPPDATA", "LANG")
# Folders of the system and of installed programs. Korvin refuses them as the chosen folder.
SYSTEM_FOLDERS = ("/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/sbin", "/sys", "/usr", "/System", "/Library")
WINDOWS_SYSTEM_FOLDERS = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")  # names of variables

# One strict pattern: "http://", a plain host or [IPv6 address], an optional port, a simple path.
# Anything else does not match. Korvin uses only this parser, so two parsers cannot disagree about a host.
BASE_URL_PATTERN = r"http://(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+)(?::(\d{1,5}))?(/[A-Za-z0-9._~/-]*)?"


class ConfigError(Exception):
    """The settings are missing, unreadable, or not allowed."""


@dataclass(frozen=True)
class Provider:
    """One model service that Korvin can talk to."""
    name: str
    base_url: str
    remote: bool


@dataclass(frozen=True)
class Settings:
    """The checked settings for one Korvin session."""
    model: str | None
    provider: Provider
    folder: Path | None  # the real path of the folder that the file tools may use, or None for no folder
    notes_file: Path  # Korvin creates this file only when it saves the first note
    log_file: Path | None = None  # the sealed log, or None for no log
    servers: dict = field(default_factory=dict)  # each tool server that the user added, by name
    source: Path | None = None  # the settings file, where Korvin stores the user's approval of server tools


def load_settings(path: str | None = None, model: str | None = None, folder: str | None = None) -> Settings:
    """Find, read, and check the settings. A model name or folder given here replaces the file's value."""
    data = dict(DEFAULTS)
    file_path = find_settings_file(path)
    if file_path is not None:
        data.update(read_settings_file(file_path))
    if model is not None:
        data["model"] = model
    if folder is not None:
        data["folder"] = folder
    return check_settings(data, file_path)


def find_settings_file(path: str | None) -> Path | None:
    """Return the settings file to use, or None to use the built-in defaults."""
    if path is not None:
        return Path(path)
    env_path = os.environ.get("KORVIN_CONFIG")
    if env_path:
        return Path(env_path)
    if Path("korvin.json").is_file():
        return Path("korvin.json")
    saved = user_data_dir() / SETTINGS_NAME
    return saved if saved.is_file() else None


def write_settings(path: str | Path, **changes: object) -> None:
    """Write the changed settings, such as the model, into the settings file. Keep the other settings that it has."""
    file = Path(path)
    data = read_settings_file(file) if file.is_file() else {}
    data.update(changes)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_settings_file(path: Path) -> dict:
    """Read one settings file and return its JSON object."""
    try:
        # "utf-8-sig" also accepts files that Windows tools save with a byte-order mark.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ConfigError(f"Korvin cannot read the settings file {path}: {error.strerror or error}.") from None
    except ValueError as error:
        # ValueError covers both bad UTF-8 and bad JSON.
        raise ConfigError(f"The settings file {path} is not valid JSON: {error}.") from None
    if not isinstance(data, dict):
        raise ConfigError(f"The settings file {path} must hold one JSON object.")
    return data


def check_settings(data: dict, source: Path | None = None) -> Settings:
    """Check every setting and return the result as Settings."""
    check_keys(data, TOP_KEYS, "the settings")
    model = data["model"]
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ConfigError('The model name must be text, such as "your-model-name".')
    providers = data["providers"]
    if not isinstance(providers, dict):
        raise ConfigError('The "providers" setting must be a JSON object.')
    checked = {name: check_provider(name, entry) for name, entry in providers.items()}
    name = data["provider"]
    if not isinstance(name, str) or name not in checked:
        raise ConfigError(f'The provider "{name}" is not in the "providers" setting.')
    folder = check_folder(data["folder"])
    notes_file, log_file = (check_data_file(data[key], key) for key in DATA_FILES)
    servers = check_servers(data["servers"])
    return Settings(model, checked[name], folder, notes_file, log_file, servers, source)


def check_servers(value: object) -> dict:
    """Check the tool servers in the settings, and return them by name."""
    if not isinstance(value, dict):
        raise ConfigError('The "servers" setting must be a JSON object.')
    for name, entry in value.items():
        where = f'the tool server "{name}"'
        if not re.fullmatch(SERVER_NAME, name):
            raise ConfigError(f"The name of {where} must be 1 to 16 small letters and digits, starting with a letter.")
        if not isinstance(entry, dict) or set(entry) != SERVER_KEYS or entry["risk"] not in RISKS:
            raise ConfigError(f'The settings for {where} need "command", "env", "approved", and "risk": read or write.')
        lists = [entry["command"], entry["env"]]
        if not entry["command"] or not all(isinstance(x, list) and all(isinstance(y, str) for y in x) for x in lists):
            raise ConfigError(f'The "command" and "env" settings for {where} must be lists of text.')
        approved = entry["approved"]
        if not isinstance(approved, dict) or not all(isinstance(a, dict) and "sha256" in a for a in approved.values()):
            raise ConfigError(f'The "approved" setting for {where} is damaged. Remove the server and add it again.')
    return dict(value)


def child_environment(names: list[str]) -> dict[str, str]:
    """Return the small environment of a tool server: CHILD_VARIABLES, and the variables that the user named."""
    return {name: os.environ[name] for name in (*CHILD_VARIABLES, *names) if name in os.environ}


def check_folder(value: object) -> Path | None:
    """Return the real path of the chosen folder, or None if no folder is chosen.

    Korvin reads files in this folder without a question, so a folder that holds too much is refused.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError('The "folder" setting must be the path of a folder, or null.')
    # A network folder sends each file request to another computer. Check the text before Korvin touches the path.
    # A mapped network drive, such as Z:, becomes a network path only when Korvin finds its real path.
    folder = None if is_network_path(value) else Path(os.path.realpath(value))
    if folder is None or is_network_path(str(folder)):
        raise ConfigError(f'The folder "{value}" is on another computer. Choose a folder on this computer.')
    if not folder.is_dir():
        raise ConfigError(f'The folder "{value}" does not exist or is not a folder.')
    home = Path(os.path.realpath(Path.home()))
    if folder.parent == folder or folder == home or folder in home.parents:
        raise ConfigError(
            f'The folder "{folder}" is too broad. Choose a smaller folder, not a whole drive or your home folder.'
        )
    if any(folder == system or system in folder.parents for system in system_folders()):
        raise ConfigError(f'The folder "{folder}" holds the system or installed programs. Choose a folder of your own.')
    return folder


def system_folders() -> list[Path]:
    """Return the real paths of the folders that hold the system and the installed programs."""
    found = [os.environ.get(name) for name in WINDOWS_SYSTEM_FOLDERS] if sys.platform == "win32" else SYSTEM_FOLDERS
    return [Path(os.path.realpath(path)) for path in found if path]


def is_network_path(text: str) -> bool:
    """Return True for a Windows network path, such as \\\\server\\share."""
    return text[:2] in ("\\\\", "//", "\\/", "/\\")


def check_data_file(value: object, key: str) -> Path:
    """Return the full path of the notes file or the log file. Korvin does not create it here."""
    if value is None:
        return user_data_dir() / DATA_FILES[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f'The "{key}" setting must be the path of a file, or null.')
    return Path(os.path.abspath(value))


def user_data_dir() -> Path:
    """Return the folder where Korvin keeps its own data, by the custom of each system."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Korvin"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Korvin"
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
    # The XDG rules say to ignore this setting when it is not an absolute path.
    return (Path(xdg_data_home) if os.path.isabs(xdg_data_home) else Path.home() / ".local" / "share") / "korvin"


def check_keys(data: dict, allowed: set[str], where: str) -> None:
    """Refuse any key that Korvin does not know."""
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"Unknown setting {', '.join(unknown)} in {where}.")


def check_provider(name: str, entry: object) -> Provider:
    """Check one provider entry and return it as a Provider."""
    where = f'the provider "{name}"'
    if not isinstance(entry, dict):
        raise ConfigError(f"The settings for {where} must be a JSON object.")
    check_keys(entry, PROVIDER_KEYS, where)
    if set(entry) != PROVIDER_KEYS:
        raise ConfigError(f'The settings for {where} need both "base_url" and "remote".')
    if entry["remote"] is not False:
        raise ConfigError(f'The settings for {where} must have "remote": false. Hosted models are not supported yet.')
    base_url = entry["base_url"]
    if not isinstance(base_url, str):
        raise ConfigError(f'The "base_url" setting for {where} must be text.')
    host, _port, _path = parse_base_url(base_url)
    if not guard.is_loopback_host(host):
        raise ConfigError(f"Korvin refuses {base_url} for {where}. Only this computer is allowed.")
    return Provider(name=name, base_url=base_url, remote=False)


def parse_base_url(url: str) -> tuple[str, int, str]:
    """Split a base URL into host, port, and path. Refuse a URL that is not plain http."""
    match = re.fullmatch(BASE_URL_PATTERN, url)
    if match is None:
        raise ConfigError(f'The address "{url}" is not allowed. Use a plain http address, such as {DEFAULT_BASE_URL}.')
    host = match.group(1).strip("[]")
    port = int(match.group(2) or "80")
    if not 1 <= port <= 65535:
        raise ConfigError(f'The port in the address "{url}" is not valid.')
    return host, port, match.group(3) or ""
