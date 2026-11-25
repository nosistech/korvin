"""Static checks on the korvin package: one network door, one file that starts programs, file access in three files
only, no code from text, standard library only, small size."""

import ast
import sys
import unittest
from pathlib import Path

KORVIN_DIR = Path(__file__).resolve().parent.parent / "korvin"
# Modules that can reach the network, or load code by name. Only door.py may import them.
DOOR_ONLY_MODULES = {
    "socket", "http", "urllib", "ssl", "ftplib", "smtplib", "asyncio",
    "importlib", "ctypes", "multiprocessing", "socketserver", "xmlrpc",
    "telnetlib", "poplib", "imaplib", "nntplib", "webbrowser",
}
# The module that starts other programs. Only mcp.py may import it, to start the tool servers that the user added.
PROCESS_MODULES = {"subprocess"}
PROCESS_FILE = "mcp.py"
# Names that run text as code or import by name. No korvin file may use them.
BANNED_NAMES = {"__import__", "eval", "exec", "compile"}
# Modules that read, write, or remove files. Only the files in FILE_USERS may import them or use the name "open".
FILE_MODULES = {
    "os", "pathlib", "io", "shutil", "tempfile", "glob", "fileinput", "filecmp", "codecs",
    "zipfile", "tarfile", "gzip", "bz2", "lzma", "sqlite3", "dbm", "shelve", "pickle", "mmap", "linecache",
}
FILE_USERS = {"tools.py", "config.py", "seal.py"}
LINE_LIMIT = 5000  # the cap: a ceiling, not a target


def imported_modules(source: str) -> set[str]:
    """Return the top-level name of every module that the source imports."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                names.add("korvin")  # a relative import stays inside the korvin package
            else:
                names.add(node.module.split(".")[0])
    return names


def used_names(source: str) -> set[str]:
    """Return every plain name, attribute name, and imported name in the source."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name)
    return names


def korvin_files() -> list[Path]:
    return sorted(KORVIN_DIR.glob("*.py"))


class OneDoorTest(unittest.TestCase):
    def test_checker_sees_both_import_forms(self) -> None:
        source = "import http.client\nfrom urllib import request\nfrom . import guard\n"
        self.assertEqual(imported_modules(source), {"http", "urllib", "korvin"})

    def test_name_checker_sees_each_form(self) -> None:
        source = "eval('1')\nbuiltins.exec\nfrom builtins import compile\nx = __import__\n"
        self.assertLessEqual(BANNED_NAMES, used_names(source))

    def test_package_has_the_door(self) -> None:
        self.assertIn("door.py", [path.name for path in korvin_files()])

    def test_only_mcp_starts_programs(self) -> None:
        self.assertIn(PROCESS_FILE, [path.name for path in korvin_files()])
        for path in korvin_files():
            if path.name == PROCESS_FILE:
                continue
            with self.subTest(path.name):
                used = imported_modules(path.read_text(encoding="utf-8")) & PROCESS_MODULES
                self.assertEqual(used, set(), f"{path.name} imports modules that only {PROCESS_FILE} may import")

    def test_only_door_uses_the_network(self) -> None:
        for path in korvin_files():
            if path.name == "door.py":
                continue
            with self.subTest(path.name):
                used = imported_modules(path.read_text(encoding="utf-8")) & DOOR_ONLY_MODULES
                self.assertEqual(used, set(), f"{path.name} imports modules that only door.py may import")

    def test_only_tools_and_config_use_files(self) -> None:
        self.assertIn("gate.py", [path.name for path in korvin_files()])
        for path in korvin_files():
            if path.name in FILE_USERS:
                continue
            with self.subTest(path.name):
                source = path.read_text(encoding="utf-8")
                used = imported_modules(source) & FILE_MODULES
                self.assertEqual(used, set(), f"{path.name} imports modules that only {FILE_USERS} may import")
                self.assertNotIn("open", used_names(source), f"{path.name} uses the name open")

    def test_file_checker_sees_open(self) -> None:
        for source in ["open('x')", "f = open", "io.open('x')", "from io import open", "Path('x').open()"]:
            with self.subTest(source):
                self.assertIn("open", used_names(source))

    def test_no_code_from_text(self) -> None:
        for path in korvin_files():
            with self.subTest(path.name):
                used = used_names(path.read_text(encoding="utf-8")) & BANNED_NAMES
                self.assertEqual(used, set(), f"{path.name} uses {', '.join(sorted(used))}")

    def test_standard_library_only(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"korvin"}
        for path in korvin_files():
            with self.subTest(path.name):
                outside = imported_modules(path.read_text(encoding="utf-8")) - allowed
                self.assertEqual(outside, set(), f"{path.name} imports modules outside the standard library")

    def test_size_limit(self) -> None:
        total = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in korvin_files())
        self.assertLessEqual(total, LINE_LIMIT)


if __name__ == "__main__":
    unittest.main()
