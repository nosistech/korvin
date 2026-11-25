"""Tests for korvin.mcp: the client for local tool servers, with the test servers of both protocol versions."""

import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from korvin import config, mcp

TESTS = Path(__file__).resolve().parent
LEGACY = [sys.executable, str(TESTS / "server_legacy.py")]
MODERN = [sys.executable, str(TESTS / "server_modern.py")]
BAD = [sys.executable, str(TESTS / "server_bad.py")]
EXAMPLE = [sys.executable, str(TESTS.parent / "examples" / "clock_server.py")]
META_KEYS = {"io.modelcontextprotocol/protocolVersion", "io.modelcontextprotocol/clientInfo",
             "io.modelcontextprotocol/clientCapabilities"}


def started(command: list[str]) -> mcp.Server:
    """Return a started server. The test closes it at the end."""
    server = mcp.Server(command, config.child_environment([]))
    server.start()
    return server


def fake_server(*lines: bytes, era: str = "legacy") -> mcp.Server:
    """Return a server with no process: it reads the given lines, and keeps what Korvin writes in server.written."""
    server = mcp.Server(["none"], {})
    server.process, server.era = SimpleNamespace(stdin=io.BytesIO()), era
    server.written = server.process.stdin
    for line in lines:
        server.lines.put(line)
    return server


def sent(server: mcp.Server) -> list[dict]:
    """Return the messages that Korvin wrote to a fake server."""
    return [json.loads(line) for line in server.written.getvalue().splitlines()]


class ServerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.record = Path(temp.name) / "received.jsonl"

    def use(self, command: list[str]) -> mcp.Server:
        server = started(command)
        self.addCleanup(server.close)
        return server

    def received(self) -> list[dict]:
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines()]


class LegacyTest(ServerTestCase):
    def test_handshake_after_the_probe(self) -> None:
        server = self.use([*LEGACY, str(self.record)])
        self.assertEqual((server.era, server.version), ("legacy", "2025-06-18"))
        self.assertEqual([tool["name"] for tool in server.tools()], ["echo", "add"])
        self.assertEqual(server.call("add", {"a": 2, "b": 3}), ("5", False))
        probe, initialize, initialized, listing, call = self.received()
        self.assertEqual(probe["method"], "server/discover")
        self.assertEqual(set(probe["params"]["_meta"]), META_KEYS)
        self.assertEqual(probe["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"], "2026-07-28")
        self.assertEqual(initialize["method"], "initialize")
        self.assertEqual(initialize["params"]["protocolVersion"], "2025-11-25")
        self.assertEqual(initialize["params"]["capabilities"], {})
        self.assertEqual(initialize["params"]["clientInfo"]["name"], "korvin")
        self.assertEqual(initialized, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertNotIn("_meta", listing["params"])
        self.assertEqual(call["params"], {"name": "add", "arguments": {"a": 2, "b": 3}})
        self.assertTrue(all(message["jsonrpc"] == "2.0" for message in self.received()))

    def test_error_output_is_not_an_error(self) -> None:
        # The legacy server writes to its error output at the start. The garbage server writes much more.
        self.assertEqual(self.use(LEGACY).call("echo", {"text": "hi"}), ("hi", False))
        self.assertEqual(self.use([*BAD, "garbage"]).call("look", {}), ("looked", False))

    def test_silent_probe_falls_back(self) -> None:
        with mock.patch.object(mcp, "PROBE_TIMEOUT", 0.5):
            server = self.use([*BAD, "silent"])
        self.assertEqual(server.era, "legacy")
        self.assertEqual(server.call("look", {}), ("looked", False))

    def test_server_that_stops_at_the_probe(self) -> None:
        server = self.use([*BAD, "dies"])
        self.assertEqual(server.call("look", {}), ("looked", False))

    def test_requests_from_the_server_are_refused(self) -> None:
        # The server asks for sampling, which Korvin refuses, and sends a ping, which Korvin answers.
        self.assertEqual(self.use([*BAD, "asks"]).call("look", {}), ("s1: error -32601; p1: result", False))


class ModernTest(ServerTestCase):
    def test_every_request_carries_the_version(self) -> None:
        server = self.use([*MODERN, "normal", str(self.record)])
        self.assertEqual((server.era, server.version), ("modern", "2026-07-28"))
        self.assertEqual([tool["name"] for tool in server.tools()], ["echo", "fail", "picture"])
        self.assertEqual(server.call("echo", {"text": "hello"}), ("hello", False))
        received = self.received()
        self.assertEqual([message["method"] for message in received], ["server/discover", "tools/list", "tools/call"])
        for message in received:
            self.assertEqual(set(message["params"]["_meta"]), META_KEYS)
            self.assertEqual(message["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"], {})

    def test_tool_error_and_other_content(self) -> None:
        server = self.use([*MODERN])
        self.assertEqual(server.call("fail", {}), ("The tool broke on purpose.", True))
        self.assertEqual(server.call("picture", {}), ("[Korvin left out an item of type image.]\nA cat.", False))
        with self.assertRaisesRegex(mcp.ServerError, "reported an error: Unknown method"):
            server.call("missing", {})

    def test_unknown_version_only(self) -> None:
        server = mcp.Server([*MODERN, "future"], config.child_environment([]))
        self.addCleanup(server.close)
        with self.assertRaisesRegex(mcp.ServerError, "2027-01-01"):
            server.start()

    def test_example_server_speaks_both(self) -> None:
        self.assertEqual(self.use(EXAMPLE).era, "modern")
        with mock.patch.object(mcp, "MODERN", "2099-01-01"):  # pretend that Korvin knows only the older protocol
            server = self.use(EXAMPLE)
        self.assertEqual((server.era, server.version), ("legacy", "2025-11-25"))
        text, failed = server.call("convert", {"value": 10, "from_unit": "km", "to_unit": "mi"})
        self.assertEqual((text, failed), ("10 km = 6.21 mi", False))
        self.assertTrue(server.call("convert", {"value": 1, "from_unit": "km", "to_unit": "kg"})[1])


class MisbehaviourTest(ServerTestCase):
    def test_timeout(self) -> None:
        server = self.use([*BAD, "slow"])
        start = time.monotonic()
        with self.assertRaisesRegex(mcp.ServerError, "did not answer within 0.5 seconds"):
            server.call("look", {}, timeout=0.5)
        self.assertLess(time.monotonic() - start, 5)

    def test_timeout_sends_a_cancellation(self) -> None:
        server = fake_server()
        with self.assertRaises(mcp.ServerError):
            server.request("tools/call", {"name": "x", "arguments": {}}, 0.2)
        request, cancel = sent(server)
        self.assertEqual(cancel["method"], "notifications/cancelled")
        self.assertEqual(cancel["params"]["requestId"], request["id"])
        self.assertNotIn("id", cancel)

    def test_no_cancellation_before_the_protocol_is_known(self) -> None:
        server = fake_server(era="")
        with self.assertRaises(mcp.ServerError):
            server.request("server/discover", {}, 0.2)
        self.assertEqual([message["method"] for message in sent(server)], ["server/discover"])

    def test_line_too_long(self) -> None:
        with self.assertRaisesRegex(mcp.ServerError, "longer than 1,000,000 bytes"):
            self.use([*BAD, "toolong"]).call("look", {})

    def test_huge_result_arrives_whole(self) -> None:
        text, _failed = self.use([*BAD, "huge"]).call("look", {})
        self.assertEqual(len(text), 300_014)  # the servers module cuts it, not the client

    def test_stubborn_server_is_ended(self) -> None:
        server = self.use([*BAD, "stubborn"])
        process = server.process
        start = time.monotonic()
        server.close()
        self.assertIsNotNone(process.poll())
        self.assertLess(time.monotonic() - start, mcp.CLOSE_WAIT + 3)
        server.close()  # a second close does nothing

    def test_normal_server_stops_when_its_input_closes(self) -> None:
        server = self.use(LEGACY)
        process = server.process
        server.close()
        self.assertEqual(process.returncode, 0)

    def test_missing_program(self) -> None:
        server = mcp.Server(["korvin-no-such-program-4471"], {})
        with self.assertRaisesRegex(mcp.ServerError, "could not start the server"):
            server.start()

    def test_stopped_server(self) -> None:
        server = self.use(LEGACY)
        server.process.kill()
        server.process.wait()
        with self.assertRaisesRegex(mcp.ServerError, "stopped"):
            server.call("echo", {"text": "x"}, timeout=5)

    def test_answers_that_korvin_cannot_use(self) -> None:
        def answer(result: object) -> bytes:
            return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode() + b"\n"

        cases = [(answer({"resultType": "input_required", "inputRequests": {}}), "does not support"),
                 (answer({"resultType": "other"}), "does not support"), (answer([1]), "cannot read"),
                 (answer({"tools": "none"}), "cannot read")]
        for line, message in cases:
            with self.subTest(line), self.assertRaisesRegex(mcp.ServerError, message):
                fake_server(b"[1]\n", b"\xff\xfe\n", b'{"id": 1, "method": "x"}\n', line).tools()

    def test_old_result_without_result_type(self) -> None:
        line = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "a"}, "not a tool"]}}).encode()
        self.assertEqual(fake_server(line + b"\n").tools(), [{"name": "a"}])

    def test_server_request_in_the_new_protocol_is_ignored(self) -> None:
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "sampling/createMessage"}).encode() + b"\n"
        answer = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}).encode() + b"\n"
        server = fake_server(request, answer, era="modern")
        self.assertEqual(server.tools(), [])
        self.assertEqual(len(sent(server)), 1)  # only Korvin's own request; no reply to the server's request

    def test_result_text(self) -> None:
        self.assertEqual(mcp.result_text({"content": [], "structuredContent": {"a": 1}}), '{"a": 1}')
        self.assertEqual(mcp.result_text({"content": "text"}), "")
        self.assertEqual(mcp.result_text({"content": [{"type": "text", "text": 5}]}),
                         "[Korvin left out an item of type text.]")

    def test_own_process_group(self) -> None:
        # Ctrl+C in the terminal must reach only Korvin, which then stops the server itself.
        key = "creationflags" if sys.platform == "win32" else "start_new_session"
        self.assertIn(key, mcp.OWN_GROUP)

    def test_small_environment(self) -> None:
        with mock.patch.dict(os.environ, {"KORVIN_TEST_SECRET": "s3cret", "KORVIN_TEST_KEY": "k"}):
            environment = config.child_environment(["KORVIN_TEST_KEY"])
        self.assertNotIn("KORVIN_TEST_SECRET", environment)
        self.assertEqual(environment["KORVIN_TEST_KEY"], "k")
        self.assertIn("PATH", environment)
        code = "import os; print(sorted(os.environ))"
        listed = subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, text=True).stdout
        self.assertNotIn("KORVIN_TEST_SECRET", listed)


if __name__ == "__main__":
    unittest.main()
