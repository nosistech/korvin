"""Tests for korvin.config: finding, reading, and checking the settings."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from korvin import config
from korvin.config import DEFAULT_BASE_URL, ConfigError, load_settings

ROOT = Path(__file__).resolve().parent.parent


def local_settings(base_url: str = DEFAULT_BASE_URL, **extra: object) -> dict:
    data = {"model": "llama3.2", "provider": "local", "providers": {"local": {"base_url": base_url, "remote": False}}}
    data.update(extra)
    return data


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        # Work in an empty folder with no KORVIN_CONFIG, so local files cannot change the result.
        old_cwd = os.getcwd()
        os.chdir(self.folder)
        self.addCleanup(os.chdir, old_cwd)
        environ = mock.patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
        os.environ.pop("KORVIN_CONFIG", None)
        # Korvin's data folder is in the temporary folder, so the user's real settings cannot change the result.
        os.environ["APPDATA"] = os.environ["XDG_DATA_HOME"] = str(self.folder / "appdata")

    def write(self, data: object, name: str = "settings.json") -> str:
        path = self.folder / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_defaults(self) -> None:
        settings = load_settings()
        self.assertIsNone(settings.model)
        self.assertEqual(settings.provider.name, "local")
        self.assertEqual(settings.provider.base_url, "http://127.0.0.1:11434/v1")
        self.assertFalse(settings.provider.remote)
        self.assertIsNone(settings.folder)
        self.assertEqual(settings.notes_file.name, "notes.jsonl")

    def test_default_notes_file_place(self) -> None:
        data = self.folder / "data"
        if sys.platform == "win32":
            os.environ["APPDATA"] = str(data)
            expected = data / "Korvin" / "notes.jsonl"
        elif sys.platform == "darwin":
            expected = Path.home() / "Library" / "Application Support" / "Korvin" / "notes.jsonl"
        else:
            os.environ["XDG_DATA_HOME"] = str(data)
            expected = data / "korvin" / "notes.jsonl"
        self.assertEqual(load_settings().notes_file, expected)
        # Korvin creates nothing when it loads the settings.
        self.assertFalse(data.exists())
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_xdg_data_home_must_be_absolute(self) -> None:
        if sys.platform in ("win32", "darwin"):
            self.skipTest("XDG_DATA_HOME is used only on Linux and other Unix systems.")
        os.environ["XDG_DATA_HOME"] = "relative/data"
        self.assertEqual(load_settings().notes_file, Path.home() / ".local" / "share" / "korvin" / "notes.jsonl")

    def test_notes_file_setting(self) -> None:
        settings = load_settings(self.write(local_settings(notes_file="my notes.jsonl")))
        self.assertEqual(settings.notes_file, self.folder / "my notes.jsonl")
        self.assertTrue(settings.notes_file.is_absolute())
        self.assertFalse(settings.notes_file.exists())

    def test_folder_setting_and_option(self) -> None:
        (self.folder / "docs").mkdir()
        (self.folder / "other").mkdir()
        path = self.write(local_settings(folder=str(self.folder / "docs" / ".." / "docs")))
        self.assertEqual(load_settings(path).folder, Path(os.path.realpath(self.folder / "docs")))
        # The --folder option replaces the folder in the settings file.
        self.assertEqual(load_settings(path, folder="other").folder, Path(os.path.realpath(self.folder / "other")))
        self.assertTrue(load_settings(folder="docs").folder.is_absolute())

    def test_bad_folder_rejected(self) -> None:
        (self.folder / "file.txt").write_text("x", encoding="utf-8")
        cases = {
            str(self.folder / "missing"): "does not exist or is not a folder",
            str(self.folder / "file.txt"): "does not exist or is not a folder",
            "": "must be the path of a folder",
            "  ": "must be the path of a folder",
            "\\\\server\\share\\docs": "on another computer",
            "//server/share/docs": "on another computer",
        }
        for folder, message in cases.items():
            with self.subTest(folder), self.assertRaisesRegex(ConfigError, message):
                load_settings(folder=folder)

    def test_too_broad_folder_rejected(self) -> None:
        home = Path.home()
        for folder in [home, home.parent, Path(home.anchor), Path(self.folder.anchor)]:
            with self.subTest(str(folder)), self.assertRaisesRegex(ConfigError, "too broad"):
                load_settings(folder=str(folder))

    def test_system_folder_rejected(self) -> None:
        programs = self.folder / "programs"
        (programs / "app").mkdir(parents=True)
        with mock.patch.object(config, "system_folders", return_value=[Path(os.path.realpath(programs))]):
            for folder in [programs, programs / "app"]:
                with self.subTest(str(folder)), self.assertRaisesRegex(ConfigError, "holds the system"):
                    load_settings(folder=str(folder))
        if sys.platform == "win32":
            with self.assertRaisesRegex(ConfigError, "holds the system"):
                load_settings(folder=os.environ["SystemRoot"])

    def test_log_file_setting(self) -> None:
        self.assertEqual(load_settings().log_file, config.user_data_dir() / "log.jsonl")
        settings = load_settings(self.write(local_settings(log_file="my log.jsonl")))
        self.assertEqual(settings.log_file, self.folder / "my log.jsonl")
        self.assertFalse(settings.log_file.exists())
        with self.assertRaisesRegex(ConfigError, '"log_file" setting'):
            load_settings(self.write(local_settings(log_file=7)))

    def test_setup_file_found_last(self) -> None:
        self.assertIsNone(config.find_settings_file(None))
        saved = config.user_data_dir() / "settings.json"
        config.write_settings(str(saved), model="from-setup", folder=None)
        self.assertEqual(load_settings().model, "from-setup")
        self.write(local_settings(model="from-cwd"), "korvin.json")
        self.assertEqual(load_settings().model, "from-cwd")

    def test_write_settings_keeps_other_keys(self) -> None:
        path = self.write(local_settings(notes_file="n.jsonl"))
        config.write_settings(path, model="new-model", folder=str(self.folder))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(data, local_settings(model="new-model", folder=str(self.folder), notes_file="n.jsonl"))

    def test_valid_file(self) -> None:
        settings = load_settings(self.write(local_settings("http://localhost:8080/v1")))
        self.assertEqual(settings.model, "llama3.2")
        self.assertEqual(settings.provider.base_url, "http://localhost:8080/v1")

    def test_example_file_is_valid(self) -> None:
        settings = load_settings(str(ROOT / "korvin.example.json"))
        self.assertEqual(settings.model, "your-model-name")
        self.assertEqual(settings.provider.base_url, DEFAULT_BASE_URL)

    def test_model_argument_replaces_file_model(self) -> None:
        settings = load_settings(self.write(local_settings()), model="other")
        self.assertEqual(settings.model, "other")

    def test_path_order(self) -> None:
        self.write(local_settings(model="from-cwd"), "korvin.json")
        self.assertEqual(load_settings().model, "from-cwd")
        os.environ["KORVIN_CONFIG"] = self.write(local_settings(model="from-env"), "env.json")
        self.assertEqual(load_settings().model, "from-env")
        explicit = self.write(local_settings(model="from-argument"), "arg.json")
        self.assertEqual(load_settings(explicit).model, "from-argument")

    def test_missing_file_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "cannot read"):
            load_settings(str(self.folder / "missing.json"))

    def test_invalid_json_rejected(self) -> None:
        path = self.folder / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "not valid JSON"):
            load_settings(str(path))

    def test_bad_values_rejected(self) -> None:
        cases = {
            "unknown top key": local_settings(colour="blue"),
            "unknown provider key": {"providers": {"local": {"base_url": DEFAULT_BASE_URL, "remote": False, "x": 1}}},
            "missing provider key": {"providers": {"local": {"base_url": DEFAULT_BASE_URL}}},
            "unknown provider": local_settings(provider="other"),
            "empty model": local_settings(model=" "),
            "model not text": local_settings(model=5),
            "remote not bool": {"providers": {"local": {"base_url": DEFAULT_BASE_URL, "remote": "no"}}},
            "not an object": [1, 2],
            "folder not text": local_settings(folder=5),
            "folder is a list": local_settings(folder=["docs"]),
            "notes_file not text": local_settings(notes_file=False),
            "notes_file empty": local_settings(notes_file=""),
            "unknown key next to the new ones": local_settings(folder=None, notes_file=None, notes="x"),
        }
        for label, data in cases.items():
            with self.subTest(label), self.assertRaises(ConfigError):
                load_settings(self.write(data))

    def test_servers_setting(self) -> None:
        good = {"command": ["python", "server.py"], "risk": "read", "env": ["SEARCH_KEY"], "approved": {"a": {"sha256": "0"}}}
        settings = load_settings(self.write(local_settings(servers={"clock": good})))
        self.assertEqual(settings.servers, {"clock": good})
        self.assertEqual(load_settings(self.write(local_settings())).servers, {})
        cases = {
            "not an object": [good],
            "name with _": {"my_clock": good},
            "name too long": {"a" * 17: good},
            "name with capital": {"Clock": good},
            "control risk": {"clock": {**good, "risk": "control"}},
            "no risk": {"clock": {key: value for key, value in good.items() if key != "risk"}},
            "extra key": {"clock": {**good, "trust": True}},
            "empty command": {"clock": {**good, "command": []}},
            "command as text": {"clock": {**good, "command": "python server.py"}},
            "env with a number": {"clock": {**good, "env": [5]}},
            "damaged approval": {"clock": {**good, "approved": {"a": "yes"}}},
        }
        for label, servers in cases.items():
            with self.subTest(label), self.assertRaises(ConfigError):
                load_settings(self.write(local_settings(servers=servers)))

    def test_empty_model_argument_rejected(self) -> None:
        # This is what "--model ''" does. The example in the message is a neutral placeholder.
        with self.assertRaisesRegex(ConfigError, 'The model name must be text, such as "your-model-name"\\.'):
            load_settings(model="")

    def test_unknown_key_named_in_message(self) -> None:
        with self.assertRaisesRegex(ConfigError, "colour"):
            load_settings(self.write(local_settings(colour="blue")))

    def test_remote_provider_rejected(self) -> None:
        data = {"provider": "cloud", "providers": {"cloud": {"base_url": "https://api.example.com/v1", "remote": True}}}
        with self.assertRaisesRegex(ConfigError, "not supported yet"):
            load_settings(self.write(data))

    def test_non_loopback_base_url_rejected(self) -> None:
        urls = [
            "http://example.com/v1",
            "http://192.168.1.5:11434/v1",
            "https://127.0.0.1/v1",
            "http://0.0.0.0:11434/v1",
            "http://127.0.0.1@example.com/v1",
            "http://127.0.0.1:11434/v1?x=1",
            "http://127.0.0.1:99999/v1",
            "http://[::ffff:127.0.0.1]/v1",
            "ftp://127.0.0.1/v1",
            "127.0.0.1:11434",
        ]
        for url in urls:
            with self.subTest(url), self.assertRaises(ConfigError):
                load_settings(self.write(local_settings(url)))

    def test_loopback_base_urls_allowed(self) -> None:
        for url in ["http://localhost:11434/v1", "http://[::1]:11434/v1", "http://127.0.0.2/v1"]:
            with self.subTest(url):
                self.assertEqual(load_settings(self.write(local_settings(url))).provider.base_url, url)


if __name__ == "__main__":
    unittest.main()
