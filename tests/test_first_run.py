"""Tests for korvin.first_run: the guided setup, with scripted answers and the fake model service."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fake_model import FakeModel
from korvin.door import ModelDoor
from korvin.first_run import COPY_PARAMETERS, STOPPED, run_setup
from test_door import closed_port, door_for

SET_64K = {"capabilities": ["completion", "tools"], "parameters": "temperature 1\nnum_ctx                        65536"}
DEFAULT = {"capabilities": ["completion", "tools"], "parameters": "temperature 1\ntop_k 20"}
NO_TOOLS = {"capabilities": ["completion"], "parameters": "num_ctx 8192"}


class SetupTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(os.path.realpath(temp.name))
        self.chosen = self.root / "shared"
        self.chosen.mkdir()
        self.settings_file = self.root / "data" / "settings.json"

    def setup(self, fake_or_url: FakeModel | str, answers: list[str]) -> tuple[bool, str]:
        """Run the setup with scripted answers. Return its result and all printed text."""
        lines, output = iter(answers), []

        def read_line(prompt: str) -> str:
            output.append(prompt)
            try:
                return next(lines)
            except StopIteration:
                raise EOFError from None

        url = fake_or_url if isinstance(fake_or_url, str) else fake_or_url.base_url
        done = run_setup(door_for(url), str(self.settings_file), read_line, output.append)
        return done, "".join(output)

    def saved(self) -> dict:
        return json.loads(self.settings_file.read_text(encoding="utf-8"))

    def test_full_setup_with_a_64k_model(self) -> None:
        with FakeModel(models=("qwen-64k", "other"), shows={"qwen-64k": SET_64K, "other": NO_TOOLS}) as fake:
            done, output = self.setup(fake, ["5", "x", "1", str(self.chosen), "y"])
        self.assertTrue(done, output)
        self.assertIn("1. qwen-64k  1.9 GB  tools: yes  context: 65,536", output)
        self.assertIn("2. other  1.9 GB  tools: no  context: 8,192", output)
        self.assertIn("Type a number from 1 to 2.", output)
        self.assertIn("The model is set to a 65,536-token context. Good.", output)
        self.assertIn(f"Settings file: {self.settings_file}", output)
        self.assertEqual(self.saved(), {"model": "qwen-64k", "folder": str(self.chosen)})
        self.assertFalse(any("from" in request for request in fake.requests))  # no copy was made

    def test_copy_with_64k(self) -> None:
        with FakeModel(models=("qwen3.5:2b-q4_K_M",), shows={"qwen3.5:2b-q4_K_M": DEFAULT}) as fake:
            done, output = self.setup(fake, ["1", "y", "", "y"])
        self.assertTrue(done, output)
        self.assertIn("context: not set (Ollama's default)", output)
        self.assertIn("but this model is not set to that size", output)
        copy = "korvin-qwen3.5-2b-q4_K_M-64k"
        expected = {"model": copy, "from": "qwen3.5:2b-q4_K_M", "parameters": COPY_PARAMETERS, "stream": False}
        self.assertEqual(fake.requests[-1], expected)
        self.assertEqual(COPY_PARAMETERS, {"num_ctx": 65_536, "num_gpu": 999, "num_batch": 256})
        self.assertEqual(self.saved(), {"model": copy, "folder": None})
        # The summary names the copy, and Ollama makes it only after the last yes.
        self.assertIn(f"  64k copy: {copy}, which Ollama makes after your yes\n", output)
        self.assertLess(output.index("Make the copy and write the settings"), output.index("Ollama made the copy"))

    def test_copy_waits_for_the_last_yes(self) -> None:
        for answers in [["1", "y", "", "n"], ["1", "y", ""], ["1", "y"]]:
            with self.subTest(answers), FakeModel(models=("m",), shows={"m": DEFAULT}) as fake:
                done, output = self.setup(fake, answers)
            self.assertFalse(done)
            self.assertIn(STOPPED, output)
            self.assertFalse(any("from" in request for request in fake.requests))  # no /api/create request
            self.assertFalse(self.settings_file.parent.exists())

    def test_enter_refuses_the_copy(self) -> None:
        with FakeModel(models=("small",), shows={"small": NO_TOOLS}) as fake:
            done, output = self.setup(fake, ["1", "", "", "y"])
        self.assertTrue(done)
        self.assertIn("This model cannot use tools", output)
        self.assertIn("Korvin will use small. Long conversations will be cut short", output)
        self.assertNotIn("from", fake.requests[-1])  # the last request was /api/show, not /api/create
        self.assertEqual(self.saved()["model"], "small")

    def test_failed_copy_keeps_the_model(self) -> None:
        with FakeModel(models=("small",), create_status=500) as fake:
            done, output = self.setup(fake, ["1", "y", "", "y"])
        self.assertTrue(done)
        self.assertIn("tools: unknown  context: not set", output)  # /api/show failed for this model
        self.assertIn("Ollama could not make the copy. The model service returned error 500: no room\n", output)
        self.assertIn("Korvin keeps small in the settings.", output)
        self.assertEqual(self.saved()["model"], "small")
        # Ctrl+C while Ollama makes the copy also keeps the base model.
        with FakeModel(models=("small",)) as fake:
            with mock.patch.object(ModelDoor, "create_copy", side_effect=KeyboardInterrupt):
                done, output = self.setup(fake, ["1", "y", "", "y"])
        self.assertTrue(done)
        self.assertIn("Ollama could not make the copy. You pressed Ctrl+C.\nKorvin keeps small", output)
        self.assertEqual(self.saved()["model"], "small")

    def test_bad_folders_are_refused_and_asked_again(self) -> None:
        with FakeModel(models=("m",), shows={"m": SET_64K}) as fake:
            answers = ["1", str(self.root / "missing"), str(Path.home()), f'"{self.chosen}"', "y"]
            done, output = self.setup(fake, answers)
        self.assertTrue(done)
        self.assertIn("does not exist", output)
        self.assertIn("too broad", output)
        self.assertEqual(self.saved()["folder"], str(self.chosen))

    def test_no_ollama(self) -> None:
        done, output = self.setup(f"http://127.0.0.1:{closed_port()}/v1", [])
        self.assertFalse(done)
        self.assertIn("Is Ollama running?", output)
        self.assertIn("ollama serve", output)
        self.assertFalse(self.settings_file.parent.exists())

    def test_no_models(self) -> None:
        with FakeModel(models=None) as fake:
            done, output = self.setup(fake, [])
        self.assertFalse(done)
        self.assertIn("ollama pull qwen3.5:2b-q4_K_M", output)

    def test_nothing_written_without_a_yes(self) -> None:
        for answers in [["1", "", ""], ["1", "", "n"], ["1"], []]:
            with self.subTest(answers), FakeModel(models=("m",), shows={"m": SET_64K}) as fake:
                done, output = self.setup(fake, answers)
            self.assertFalse(done)
            self.assertIn(STOPPED, output)
            self.assertFalse(self.settings_file.parent.exists())

    def test_setup_again_keeps_other_settings(self) -> None:
        self.settings_file.parent.mkdir()
        self.settings_file.write_text(json.dumps({"model": "old", "notes_file": "n.jsonl"}), encoding="utf-8")
        with FakeModel(models=("m",), shows={"m": SET_64K}) as fake:
            self.setup(fake, ["1", "", "y"])
        self.assertEqual(self.saved(), {"model": "m", "notes_file": "n.jsonl", "folder": None})


if __name__ == "__main__":
    unittest.main()
