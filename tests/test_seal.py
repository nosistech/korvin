"""Tests for korvin.seal: the sealed log, its check, and what the chat records in it."""

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fake_model import FakeModel, tool_call
from korvin import seal
from korvin.chat import FULL
from korvin.seal import Log
from test_chat import ChatTestCase, run, save
from test_tools import settings_for


class SealTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(os.path.realpath(temp.name))
        self.path = self.root / "data" / "log.jsonl"

    def fill(self, count: int = 4) -> list[bytes]:
        """Add entries to the log. Return its lines."""
        log = Log(self.path)
        for number in range(count):
            log.add("tool call", tool="read_file", argument=f"file{number}.txt", outcome="9 characters", decision="rule")
        return self.path.read_bytes().splitlines(keepends=True)

    def rewrite(self, lines: list[bytes]) -> None:
        self.path.write_bytes(b"".join(lines))


class LogTest(SealTestCase):
    def test_chain(self) -> None:
        lines = self.fill(3)
        entries = [json.loads(line) for line in lines]
        self.assertEqual([entry["seq"] for entry in entries], [1, 2, 3])
        previous = seal.START
        for line, entry in zip(lines, entries):
            content = {key: value for key, value in entry.items() if key != "seal"}
            self.assertEqual(entry["seal"], seal.seal_of(previous, content))
            self.assertEqual(line, (seal.canonical(entry) + "\n").encode("ascii"))
            self.assertRegex(entry["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            previous = entry["seal"]

    def test_intact_log(self) -> None:
        lines = self.fill(3)
        intact, report = seal.check(self.path)
        self.assertTrue(intact, report)
        last = json.loads(lines[-1])["seal"]
        self.assertIn("The sealed log is intact.", report)
        self.assertIn("Entries: 3,", report)
        self.assertIn(f"Last seal: {last}", report)
        self.assertIn("Anyone who can write the file can do that", report)

    def test_tampering_is_found(self) -> None:
        cases = {
            "changed value": (lambda lines: [lines[0], lines[1].replace(b"file1", b"file9"), *lines[2:]], 2, "seal"),
            "removed line": (lambda lines: [lines[0], *lines[2:]], 2, "removed or inserted"),
            "inserted copy": (lambda lines: [lines[0], lines[0], *lines[1:]], 2, "removed or inserted"),
            "swapped lines": (lambda lines: [lines[1], lines[0], *lines[2:]], 1, "removed or inserted"),
            "extra space": (lambda lines: [lines[0], lines[1].replace(b",", b", ", 1), *lines[2:]], 2, "fixed form"),
            "not JSON": (lambda lines: [lines[0], b"hello\n", *lines[2:]], 2, "not a readable entry"),
            "cut last line": (lambda lines: [*lines[:-1], lines[-1][:-1]], 4, "cut off"),
        }
        for label, (change, number, problem) in cases.items():
            with self.subTest(label):
                self.path.unlink(missing_ok=True)
                self.rewrite(change(self.fill()))
                intact, report = seal.check(self.path)
                self.assertFalse(intact)
                self.assertIn(f"BROKEN at line {number}:", report)
                self.assertIn(problem, report)
                self.assertIn(f"The {number - 1:,} lines before it are intact.", report)

    def test_kept_seal(self) -> None:
        lines = self.fill(4)
        kept = json.loads(lines[1])["seal"]
        intact, report = seal.check(self.path, kept.upper() + " ")
        self.assertTrue(intact, report)
        self.assertIn("entries 1 to 2 are unchanged", report)
        intact, report = seal.check(self.path, "0" * 64)
        self.assertFalse(intact)
        self.assertIn("not in the log", report)

    def test_rebuilt_chain_fails_only_against_a_kept_seal(self) -> None:
        lines = self.fill(3)
        kept = json.loads(lines[-1])["seal"]
        # Someone changes entry 2 and rebuilds every seal after it. The chain alone looks intact.
        entries = [json.loads(line) for line in lines]
        entries[1]["argument"] = "secret.txt"
        previous, rebuilt = seal.START, []
        for entry in entries:
            entry.pop("seal")
            entry["seal"] = previous = seal.seal_of(previous, entry)
            rebuilt.append((seal.canonical(entry) + "\n").encode("ascii"))
        self.rewrite(rebuilt)
        self.assertTrue(seal.check(self.path)[0])
        self.assertFalse(seal.check(self.path, kept)[0])

    def test_no_log(self) -> None:
        intact, report = seal.check(self.path)
        self.assertFalse(intact)
        self.assertIn("There is no sealed log", report)
        self.assertIn("nothing to show", seal.table(self.path, 5))
        self.assertFalse(self.path.parent.exists())

    def test_table(self) -> None:
        self.fill(5)
        with open(self.path, "a", encoding="ascii") as file:
            file.write("broken\n")
        table = seal.table(self.path, 3)
        self.assertIn("The last 3 of 6 entries", table)
        self.assertIn('read_file "file4.txt" -> 9 characters (rule)', table)
        self.assertNotIn("file2.txt", table)
        self.assertIn("(a line that Korvin cannot read)", table)
        self.assertIn("does not check the seals", table)

    def test_failed_write_is_said_once(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.mkdir()  # a folder where the log file should be, so every write fails
        said: list[str] = []
        log = Log(self.path, said.append)
        log.add("session start")
        log.add("tool call")
        self.assertEqual(len(said), 1)
        self.assertIn("Korvin cannot keep its sealed log", said[0])
        self.assertEqual(log.closing(), "")

    def test_damaged_last_line_stops_the_log(self) -> None:
        self.rewrite([*self.fill(2), b'{"seq": 3, "se'])
        said: list[str] = []
        Log(self.path, said.append).add("session start")
        self.assertIn("the last line of the log is damaged", said[0])
        self.assertTrue(self.path.read_bytes().endswith(b'"se'))  # Korvin added nothing to a broken log

    def test_two_logs_make_one_chain(self) -> None:
        first, second = Log(self.path), Log(self.path)
        for log in (first, second, first, second):
            log.add("session start")
        self.assertTrue(seal.check(self.path)[0])
        self.assertIn("Last seal of the log: " + second.seal, second.closing())


class ChatLogTest(ChatTestCase):
    def log_settings(self, fake: FakeModel):
        self.log_file = self.folder.parent / "data" / "log.jsonl"
        return replace(settings_for(self.folder, self.notes_file, fake.base_url), log_file=self.log_file)

    def entries(self) -> list[dict]:
        return [json.loads(line) for line in self.log_file.read_text(encoding="ascii").splitlines()]

    def test_chat_records_actions_not_content(self) -> None:
        script = [
            tool_call("read_file", json.dumps({"path": "plan.txt"})), [{"content": "Read."}],
            save("Buy milk " + "x" * 100), [{"content": "Saved."}],
            tool_call("delete_all", "{}"), [{"content": "No."}],
        ]
        lines = ["/rule Answer in Spanish.", "read plan.txt please", "save a note", "", "delete", "/rule clear"]
        with FakeModel(script=script) as fake:
            code, output = run(self.log_settings(fake), lines)
        self.assertEqual(code, 0)
        entries = self.entries()
        events = [entry["event"] for entry in entries]
        self.assertEqual(
            events, ["session start", "rule added", "tool call", "tool call", "tool call", "rules cleared", "session end"]
        )
        self.assertEqual(entries[0]["folder"], str(self.folder))
        self.assertEqual(entries[0]["model"], "fake-model")
        read, note, unknown = entries[2:5]
        self.assertEqual((read["tool"], read["argument"], read["decision"]), ("read_file", "plan.txt", "allowed by rule"))
        self.assertEqual((note["outcome"], note["decision"]), ("you said no", "user said no"))
        self.assertEqual(len(note["argument"]), 60)  # the shortened text, as the action line shows it
        self.assertEqual(unknown["decision"], "denied: unknown tool")
        text = self.log_file.read_text(encoding="ascii")
        for content in ["The plan.", "read plan.txt please", "x" * 61, "Read.", "Hello"]:
            self.assertNotIn(content, text)
        self.assertTrue(seal.check(self.log_file)[0])
        self.assertTrue(output.endswith(seal.CLOSING.format(seal=entries[-1]["seal"])))

    def test_full_and_removed_turns_are_recorded(self) -> None:
        with FakeModel(usage=True, context=6_000) as fake:
            _code, output = run(self.log_settings(fake), ["hi", "x" * 2_000])
        self.assertIn(FULL, output)
        events = [entry["event"] for entry in self.entries()]
        self.assertEqual(events[-3:], ["conversation full", "turn removed", "session end"])

    def test_session_grant_is_recorded(self) -> None:
        script = [save("one"), [{"content": "ok"}], save("two"), [{"content": "ok"}]]
        with FakeModel(script=script) as fake:
            run(self.log_settings(fake), ["save one", "s", "save two"])
        decisions = [entry.get("decision") for entry in self.entries() if entry["event"] == "tool call"]
        self.assertEqual(decisions, ["user said yes for the session", "user said yes for the session earlier"])

    def test_setup_warning(self) -> None:
        with FakeModel(gpu=0.7) as fake:
            _code, output = run(self.log_settings(fake), ["hi", "again"])
        self.assertEqual(output.count("Warning: the model runs 70% on the graphics card"), 1)
        with FakeModel(gpu=1.0) as fake:
            _code, output = run(self.log_settings(fake), ["hi"])
        self.assertNotIn("Warning:", output)


if __name__ == "__main__":
    unittest.main()
