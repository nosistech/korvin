"""Tests for korvin.tools: the four built-in tools and the folder check."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from korvin import tools
from korvin.config import Provider, Settings
from korvin.tools import FIND_LIMIT, LIST_LIMIT, NOTE_LIMIT, OUTSIDE, READ_LIMIT, RESULT_LIMIT, Result, ToolError

OUTSIDE_SUMMARY = "refused: outside the chosen folder"


def settings_for(folder: Path | None, notes_file: Path, base_url: str = "http://127.0.0.1:1/v1") -> Settings:
    provider = Provider(name="local", base_url=base_url, remote=False)
    return Settings(model="fake-model", provider=provider, folder=folder, notes_file=notes_file)


def make_link(link: Path, target: Path) -> bool:
    """Make a link to a folder: a symlink, or a junction on Windows. Return False if the system refuses both."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        pass
    if sys.platform != "win32":
        return False
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    return result.returncode == 0 and link.is_dir()


class ToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(os.path.realpath(temp.name))
        self.folder = self.root / "chosen"
        self.folder.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("SECRET", encoding="utf-8")
        (self.folder / "plan.txt").write_text("The plan.", encoding="utf-8")
        self.notes_file = self.root / "data" / "notes.jsonl"
        self.settings = settings_for(self.folder, self.notes_file)

    def call(self, name: str, arguments: object) -> Result:
        """Check the arguments and run the tool, as chat.py does after the gate allows it."""
        try:
            value = tools.argument(name, arguments)
        except ToolError as error:
            return Result(str(error), error.summary)
        return tools.run(self.settings, name, value)


class SchemaTest(unittest.TestCase):
    def test_schemas(self) -> None:
        self.assertEqual(list(tools.TOOLS), ["list_folder", "read_file", "save_note", "find_note"])
        for name, tool in tools.TOOLS.items():
            with self.subTest(name):
                function = tool.schema["function"]
                self.assertEqual(tool.schema["type"], "function")
                self.assertEqual(function["name"], name)
                self.assertTrue(function["description"].endswith("."))
                self.assertEqual(function["parameters"]["required"], [tool.argument])
                self.assertEqual(list(function["parameters"]["properties"]), [tool.argument])
                self.assertIs(function["parameters"]["additionalProperties"], False)
        self.assertEqual(tools.SCHEMAS, [tool.schema for tool in tools.TOOLS.values()])
        self.assertIn('Use "." for the chosen folder', tools.LIST_FOLDER["function"]["description"])
        self.assertIn("Notes are not files", tools.FIND_NOTE["function"]["description"])


class FileToolTest(ToolTestCase):
    def test_list_folder(self) -> None:
        (self.folder / "docs").mkdir()
        (self.folder / "b.txt").write_text("b", encoding="utf-8")
        (self.folder / "A.txt").write_text("a", encoding="utf-8")
        result = self.call("list_folder", {"path": "."})
        self.assertEqual(result.text, "4 entries. Folder names end with /.\nA.txt\nb.txt\ndocs/\nplan.txt")
        self.assertEqual(result.summary, "4 entries")
        self.assertEqual(self.call("list_folder", {"path": str(self.folder / "docs")}).summary, "0 entries")

    def test_list_folder_limit(self) -> None:
        many = self.folder / "many"
        many.mkdir()
        for number in range(LIST_LIMIT + 5):
            (many / f"file{number:03}.txt").write_text("", encoding="utf-8")
        lines = self.call("list_folder", {"path": "many"}).text.split("\n")
        self.assertEqual(len(lines), 1 + LIST_LIMIT + 1)
        self.assertEqual(lines[1], "file000.txt")
        self.assertEqual(lines[-1], "... and 5 more.")

    def test_list_folder_needs_a_folder(self) -> None:
        self.assertEqual(self.call("list_folder", {"path": "plan.txt"}).summary, "error: not a folder")

    def test_read_file(self) -> None:
        self.assertEqual(self.call("read_file", {"path": "plan.txt"}), Result("The plan.", "9 characters", outside=True))
        self.assertEqual(self.call("read_file", {"path": str(self.folder / "plan.txt")}).text, "The plan.")
        (self.folder / "bom.txt").write_bytes(b"\xef\xbb\xbfcaf\xc3\xa9")
        self.assertEqual(self.call("read_file", {"path": "bom.txt"}).text, "café")
        (self.folder / "empty.txt").write_bytes(b"")
        self.assertEqual(self.call("read_file", {"path": "empty.txt"}), Result("The file is empty.", "0 characters", outside=True))

    def test_read_missing_file_or_folder(self) -> None:
        for path in ["missing.txt", "."]:
            with self.subTest(path):
                self.assertEqual(self.call("read_file", {"path": path}).summary, "error: no such file")

    def test_read_size_limit(self) -> None:
        (self.folder / "full.txt").write_bytes(b"a" * READ_LIMIT)
        result = self.call("read_file", {"path": "full.txt"})
        self.assertEqual(result.summary, "200,000 characters, cut to 20,000")
        self.assertEqual(len(result.text), RESULT_LIMIT)
        (self.folder / "big.txt").write_bytes(b"a" * (READ_LIMIT + 1))
        result = self.call("read_file", {"path": "big.txt"})
        self.assertEqual(result.summary, "refused: file too large")
        self.assertIn("200,000 bytes", result.text)

    def test_read_refuses_text_that_is_not_utf8(self) -> None:
        files = {"latin1.txt": b"caf\xe9", "binary.bin": b"MZ\x00\x01\x02", "utf16.txt": "hi".encode("utf-16")}
        for name, data in files.items():
            with self.subTest(name):
                (self.folder / name).write_bytes(data)
                result = self.call("read_file", {"path": name})
                self.assertEqual(result.summary, "refused: not UTF-8 text")
                self.assertIn("only UTF-8 text files", result.text)

    def escapes(self) -> list[str]:
        """Return paths that point outside the chosen folder, or that are not plain file paths."""
        paths = [
            "..", "../outside/secret.txt", "..\\outside\\secret.txt", "sub/../../outside/secret.txt",
            str(self.outside / "secret.txt"), str(self.root),
            "\\\\server\\share\\secret.txt", "//server/share/secret.txt", "\\/server/share",
            "\\\\.\\C:\\secret.txt", "\\\\?\\" + str(self.folder / "plan.txt"),
            "CON", "nul", "nul.txt", "Aux ", "sub/COM1", "LPT1.log", "conin$",
            "plan.txt:secret", "plan.txt::$DATA", "plan\0.txt",
        ]
        if sys.platform == "win32":
            other = "Q" if not self.folder.drive.upper().startswith("Q") else "R"
            # Root-relative, other-drive, and drive-relative paths.
            paths += ["\\outside\\secret.txt", f"{other}:\\secret.txt", f"{other}:secret.txt", "C:plan.txt"]
        else:
            paths += ["/etc/passwd"]
        return paths

    def test_paths_outside_the_folder_refused(self) -> None:
        for path in self.escapes():
            for name in ["read_file", "list_folder"]:
                with self.subTest(path=path, tool=name):
                    self.assertEqual(self.call(name, {"path": path}), Result(OUTSIDE, OUTSIDE_SUMMARY))

    def test_empty_path_means_the_chosen_folder(self) -> None:
        listing = self.call("list_folder", {"path": "."})
        for path in ["", "   ", "\t", " \n "]:
            with self.subTest(repr(path)):
                self.assertEqual(self.call("list_folder", {"path": path}), listing)
                # The chosen folder is not a file, so read_file says so. It does not say "outside".
                self.assertEqual(self.call("read_file", {"path": path}).summary, "error: no such file")

    def test_messages_tell_the_model_how_to_recover(self) -> None:
        self.assertIn("relative to the chosen folder", OUTSIDE)
        self.assertIn('list_folder with "."', OUTSIDE)
        for name, path in [("list_folder", "plan.txt"), ("list_folder", "docs"), ("read_file", "missing.txt")]:
            with self.subTest(name=name, path=path):
                self.assertIn('Use list_folder with "." to see the real names.', self.call(name, {"path": path}).text)

    def test_messages_never_show_the_folder(self) -> None:
        paths = self.escapes() + ["plan.txt", "docs", "missing.txt", "sub/missing.txt", ".", ""]
        for path in paths:
            for name in ["read_file", "list_folder"]:
                with self.subTest(path=path, tool=name):
                    text = self.call(name, {"path": path}).text
                    for hidden in [str(self.folder), str(self.root), self.root.name]:
                        self.assertNotIn(hidden, text)

    def test_link_to_outside_refused(self) -> None:
        if not make_link(self.folder / "link", self.outside):
            self.skipTest("This system refused to make a symlink or a junction.")
        self.assertEqual(self.call("read_file", {"path": "link/secret.txt"}).summary, OUTSIDE_SUMMARY)
        self.assertEqual(self.call("list_folder", {"path": "link"}).summary, OUTSIDE_SUMMARY)
        # The link itself is only a name in the listing.
        self.assertIn("link/", self.call("list_folder", {"path": "."}).text)

    def test_link_inside_allowed(self) -> None:
        (self.folder / "docs").mkdir()
        (self.folder / "docs" / "a.txt").write_text("A", encoding="utf-8")
        if not make_link(self.folder / "inner", self.folder / "docs"):
            self.skipTest("This system refused to make a symlink or a junction.")
        self.assertEqual(self.call("read_file", {"path": "inner/a.txt"}).text, "A")

    def test_file_symlink_to_outside_refused(self) -> None:
        try:
            os.symlink(self.outside / "secret.txt", self.folder / "secret.txt")
        except OSError:
            self.skipTest("This system refused to make a file symlink.")
        self.assertEqual(self.call("read_file", {"path": "secret.txt"}).summary, OUTSIDE_SUMMARY)

    def test_no_folder_chosen(self) -> None:
        self.settings = settings_for(None, self.notes_file)
        for name in ["read_file", "list_folder"]:
            with self.subTest(name):
                result = self.call(name, {"path": "plan.txt"})
                self.assertIn("no folder chosen", result.summary)
                self.assertIn("--folder PATH", result.text)
        self.assertEqual(self.call("find_note", {"query": ""}).summary, "no notes yet")


class ArgumentTest(ToolTestCase):
    def test_wrong_arguments(self) -> None:
        keys = {"list_folder": "path", "read_file": "path", "save_note": "text", "find_note": "query"}
        for name, key in keys.items():
            for arguments in [{}, {key: 5}, {key: None}, {key: "x", "extra": "y"}, {"wrong": "x"}, [key], "x", None]:
                with self.subTest(name=name, arguments=arguments):
                    result = self.call(name, arguments)
                    self.assertEqual(result.summary, "error: wrong arguments")
                    self.assertIn(f'{{"{key}": "<text>"}}', result.text)
                    self.assertIn(name, result.text)

    def test_unknown_tool(self) -> None:
        result = self.call("delete_file", {"path": "plan.txt"})
        self.assertEqual(result.summary, "refused: unknown tool")
        self.assertEqual(tools.run(self.settings, "delete_file", "plan.txt").summary, "refused: unknown tool")


class NoteTest(ToolTestCase):
    def save(self, text: str) -> Result:
        return self.call("save_note", {"text": text})

    def test_nothing_created_until_save(self) -> None:
        self.assertEqual(self.call("find_note", {"query": "milk"}), Result("No notes yet.", "no notes yet"))
        self.assertFalse(self.notes_file.parent.exists())
        self.assertEqual(self.save("Buy milk"), Result("Saved the note.", "saved"))
        lines = self.notes_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        note = json.loads(lines[0])
        self.assertEqual(set(note), {"time", "text"})
        self.assertEqual(note["text"], "Buy milk")
        self.assertIsNotNone(datetime.fromisoformat(note["time"]).tzinfo)

    def test_note_limit(self) -> None:
        self.assertEqual(self.save("x" * NOTE_LIMIT).summary, "saved")
        self.assertEqual(self.save("x" * (NOTE_LIMIT + 1)).summary, "error: note too long")
        for text in ["", "   \n"]:
            with self.subTest(text):
                self.assertEqual(self.save(text).summary, "error: empty note")
        self.assertEqual(len(self.notes_file.read_text(encoding="utf-8").splitlines()), 1)

    def test_find_matches_every_word_in_any_case(self) -> None:
        for text in ["Buy milk", "Call Anna about the MILK", "Plan the trip", "Ünïcode Straße"]:
            self.save(text)
        found = self.call("find_note", {"query": "milk"})
        self.assertEqual((found.summary, found.outside), ("2 notes", True))
        texts = [line.split(": ", 1)[1] for line in found.text.split("\n")]
        self.assertEqual(texts, ["Call Anna about the MILK", "Buy milk"])
        self.assertIn("Call Anna", self.call("find_note", {"query": "anna MILK"}).text)
        self.assertEqual(self.call("find_note", {"query": "anna trip"}).summary, "no matching notes")
        self.assertFalse(self.call("find_note", {"query": "anna trip"}).outside)
        self.assertEqual(self.call("find_note", {"query": "STRASSE"}).summary, "1 note")

    def test_find_newest_first_and_limit(self) -> None:
        for number in range(FIND_LIMIT + 2):
            self.save(f"note {number}")
        found = self.call("find_note", {"query": "  "})
        texts = [line.split(": ", 1)[1] for line in found.text.split("\n")]
        self.assertEqual(texts, [f"note {number}" for number in range(FIND_LIMIT + 1, 1, -1)])
        self.assertEqual(found.summary, f"{FIND_LIMIT} notes")

    def test_bad_lines_skipped(self) -> None:
        self.notes_file.parent.mkdir()
        good = json.dumps({"time": "2026-01-15T10:00:00+01:00", "text": "kept"})
        self.notes_file.write_text(f"not json\n[1]\n{{\"text\": 5}}\n{good}\n", encoding="utf-8")
        self.assertEqual(self.call("find_note", {"query": ""}).text, "- 2026-01-15T10:00:00+01:00: kept")

    def test_file_system_error_becomes_a_result(self) -> None:
        self.settings = settings_for(self.folder, self.folder)  # the notes file is a folder
        result = self.save("note")
        self.assertTrue(result.summary.startswith("error: "), result.summary)
        self.assertTrue(result.text.startswith("The tool failed: "))


class ResultCapTest(unittest.TestCase):
    def test_cap(self) -> None:
        short = Result("x" * RESULT_LIMIT, "s")
        self.assertIs(tools.cap(short), short)
        long = tools.cap(Result("x" * 30_000, "s", outside=True))
        self.assertEqual(len(long.text), RESULT_LIMIT)
        self.assertTrue(long.text.endswith("[Korvin cut this result here. The full result has 30,000 characters.]"))
        self.assertEqual((long.summary, long.outside), ("s, cut to 20,000", True))


if __name__ == "__main__":
    unittest.main()
