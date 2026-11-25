"""Tests for korvin.__main__: run "python -m korvin" as a separate process."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fake_model import FakeModel
from korvin import __main__ as korvin_main
from korvin import config
from test_door import closed_port

ROOT = Path(__file__).resolve().parent.parent


def run_korvin(*args: str, input: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("KORVIN_CONFIG", None)
    command = [sys.executable, "-m", "korvin", *args]
    return subprocess.run(command, cwd=ROOT, env=env, input=input, capture_output=True, encoding="utf-8", timeout=60)


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(os.path.realpath(temp.name))

    def settings_file(self, base_url: str) -> str:
        # The notes file is in the temporary folder, so a test can never touch the user's real notes.
        data = {
            "provider": "local",
            "providers": {"local": {"base_url": base_url, "remote": False}},
            "notes_file": str(self.folder / "data" / "notes.jsonl"),
            "log_file": str(self.folder / "log" / "log.jsonl"),
        }
        path = self.folder / "settings.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_folder_option(self) -> None:
        chosen = self.folder / "chosen"
        chosen.mkdir()
        with FakeModel() as fake:
            settings = self.settings_file(fake.base_url)
            result = run_korvin("--config", settings, "--model", "fake-model", "--folder", str(chosen), input="/exit\n")
            no_folder = run_korvin("--config", settings, "--model", "fake-model", input="/exit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Folder: {chosen} (Korvin reads files here. It asks before an unexpected read.)", result.stdout)
        self.assertIn("Folder: none. File tools are off.", no_folder.stdout)
        self.assertFalse((self.folder / "data").exists())

    def test_bad_folder_option(self) -> None:
        settings = self.settings_file("http://127.0.0.1:1/v1")
        for folder, message in [(str(self.folder / "missing"), "does not exist"), (str(Path.home()), "too broad")]:
            with self.subTest(folder):
                result = run_korvin("--config", settings, "--model", "fake-model", "--folder", folder)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_version(self) -> None:
        result = run_korvin("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Korvin 0.3.0", result.stdout)

    def test_no_model_lists_installed_models(self) -> None:
        with FakeModel(models=("llama3.2", "qwen3")) as fake:
            result = run_korvin("--config", self.settings_file(fake.base_url))
        self.assertEqual(result.returncode, 2)
        self.assertIn("No model is chosen.", result.stdout)
        self.assertIn("llama3.2", result.stdout)
        self.assertIn("qwen3", result.stdout)
        self.assertIn("--model", result.stdout)

    def test_no_model_and_none_installed(self) -> None:
        with FakeModel(models=None) as fake:
            result = run_korvin("--config", self.settings_file(fake.base_url))
        self.assertEqual(result.returncode, 2)
        self.assertIn("ollama pull", result.stdout)

    def test_bad_settings(self) -> None:
        result = run_korvin("--config", self.settings_file("http://example.com/v1"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Only this computer is allowed", result.stderr)

    def test_service_not_running(self) -> None:
        result = run_korvin("--config", self.settings_file(f"http://127.0.0.1:{closed_port()}/v1"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Is Ollama running?", result.stderr)

    def test_check_and_log_commands(self) -> None:
        with FakeModel() as fake:
            settings = self.settings_file(fake.base_url)
            chat = run_korvin("--config", settings, "--model", "fake-model", input="hi\n/exit\n")
        self.assertIn("Last seal of the log: ", chat.stdout)
        check = run_korvin("check", "--config", settings)
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertIn("The sealed log is intact.", check.stdout)
        self.assertIn(chat.stdout.split("Last seal of the log: ")[1].split("\n")[0], check.stdout)
        log = run_korvin("log", "--config", settings, "--last", "1")
        self.assertEqual(log.returncode, 0)
        self.assertIn("The last 1 of 2 entries", log.stdout)
        self.assertIn("session end", log.stdout)
        path = self.folder / "log" / "log.jsonl"
        path.write_text(path.read_text(encoding="ascii").replace("fake-model", "evil-model"), encoding="ascii")
        broken = run_korvin("check", "--config", settings)
        self.assertEqual(broken.returncode, 1)
        self.assertIn("The sealed log is BROKEN at line 1", broken.stdout)


class FirstRunTest(unittest.TestCase):
    """Run main() in this process, with Korvin's data folder in a temporary folder and the setup replaced."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(os.path.realpath(temp.name))
        old_cwd = os.getcwd()
        os.chdir(self.folder)  # no korvin.json here
        self.addCleanup(os.chdir, old_cwd)
        for patch in [
            mock.patch.dict(os.environ, {"APPDATA": str(self.folder), "XDG_DATA_HOME": str(self.folder)}),
            mock.patch.object(korvin_main, "use_utf8_output"),
            mock.patch("sys.stdout", io.StringIO()),
        ]:
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("KORVIN_CONFIG", None)

    def test_no_settings_starts_the_setup(self) -> None:
        with mock.patch.object(korvin_main, "run_setup", return_value=False) as setup:
            self.assertEqual(korvin_main.main(["--model", "x"]), 2)
        self.assertEqual(setup.call_args.args[1], str(config.user_data_dir() / "settings.json"))
        self.assertEqual(list(self.folder.iterdir()), [])  # Korvin wrote no file

    def test_setup_then_chat(self) -> None:
        def setup(door: object, path: str) -> bool:
            config.write_settings(path, model="chosen-model", folder=None)
            return True

        with mock.patch.object(korvin_main, "run_setup", side_effect=setup), \
                mock.patch.object(korvin_main, "run_chat", return_value=0) as chat:
            self.assertEqual(korvin_main.main([]), 0)
            self.assertEqual(chat.call_args.args[0].model, "chosen-model")
            # Now settings exist: the chat starts at once, and the setup runs only when asked.
            self.assertEqual(korvin_main.main(["--model", "other"]), 0)
            self.assertEqual(chat.call_args.args[0].model, "other")
            self.assertEqual(korvin_main.main(["setup"]), 0)
            self.assertEqual(chat.call_count, 2)

    def test_check_and_log_write_nothing(self) -> None:
        self.assertEqual(korvin_main.main(["check"]), 1)
        self.assertEqual(korvin_main.main(["log"]), 0)
        self.assertIn("There is no sealed log", sys.stdout.getvalue())
        self.assertEqual(list(self.folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
