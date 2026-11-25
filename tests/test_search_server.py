"""Tests for examples/search_server.py, against a fake of Ollama's web search API on this computer.

No test calls the real API. The server reaches the fake only through its test-only variable, which accepts
nothing but an address on 127.0.0.1.
"""

import importlib.util
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from korvin import config, mcp, servers
from test_door import closed_port

SEARCH = Path(__file__).resolve().parent.parent / "examples" / "search_server.py"
KEY = "test-key-4471-never-shown"
spec = importlib.util.spec_from_file_location("search_server", SEARCH)
search_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search_server)


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        pass  # a client that stopped waiting is expected in the time-limit test


class FakeApi:
    """A fake of the web search API. It records each request and sends the planned reply for its path."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.replies: dict[str, tuple[int, bytes, dict]] = {}
        self.delay = 0.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                fake.requests.append({"path": self.path, "authorization": self.headers.get("Authorization"),
                                      "body": json.loads(body)})
                time.sleep(fake.delay)
                status, data, headers = fake.replies.get(self.path, (404, b'{"error": "not found"}', {}))
                self.send_response(status)
                for name, value in {**headers, "Content-Length": str(len(data))}.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:
                pass

        self.http = QuietServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def reply(self, path: str, body: object, status: int = 200, **headers: str) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.replies[path] = (status, data, headers)

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()


class SearchServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeApi()
        self.addCleanup(self.fake.close)
        self.texts: list[str] = []  # every text that the server sent back, to prove that the key is never in one

    def start(self, key: str | None = KEY, url: str | None = None) -> mcp.Server:
        """Start the search server with Korvin's own client. It reaches only the fake."""
        env = {**config.child_environment([]), search_server.TEST_VARIABLE: url or self.fake.url}
        if key is not None:
            env[search_server.KEY_VARIABLE] = key
        server = mcp.Server([sys.executable, str(SEARCH)], env)
        self.addCleanup(server.close)
        server.start()
        return server

    def call(self, server: mcp.Server, tool: str, arguments: dict) -> tuple[str, bool]:
        text, failed = server.call(tool, arguments, timeout=30)
        self.texts.append(text)
        return text, failed

    def tearDown(self) -> None:
        self.assertFalse(any(KEY in text for text in self.texts))

    def test_both_protocol_eras_and_tools_that_korvin_accepts(self) -> None:
        server = self.start()
        self.assertEqual(server.era, "modern")
        found = server.tools()
        self.assertEqual([tool["name"] for tool in found], ["search", "fetch"])
        for tool in found:
            self.assertEqual(servers.problem("search", tool), "")
            self.assertLessEqual(len(tool["description"]), servers.DESCRIPTION_LIMIT)
        with mock.patch.object(mcp, "MODERN", "2099-01-01"):  # pretend that Korvin knows only the older protocol
            server = self.start()
        self.assertEqual((server.era, server.version), ("legacy", "2025-11-25"))
        self.assertEqual([tool["name"] for tool in server.tools()], ["search", "fetch"])

    def test_search(self) -> None:
        results = [{"title": f"Tide {n}", "url": f"https://tides.example/{n}", "content": "wave " * 400}
                   for n in range(7)]
        self.fake.reply("/api/web_search", {"results": results})
        server = self.start()
        text, failed = self.call(server, "search", {"query": "  harbor tides ", "max_results": 2})
        self.assertFalse(failed)
        self.assertEqual(self.fake.requests[0], {"path": "/api/web_search", "authorization": f"Bearer {KEY}",
                                                 "body": {"query": "harbor tides", "max_results": 2}})
        self.assertTrue(text.startswith("1. Tide 0\n   https://tides.example/0\n   wave wave"))
        self.assertIn("2. Tide 1\n", text)
        self.assertNotIn("Tide 2", text)  # never more results than asked for
        self.assertEqual(text.count("[cut to 500 characters]"), 2)
        self.call(server, "search", {"query": "harbor"})
        self.assertEqual(self.fake.requests[1]["body"], {"query": "harbor", "max_results": 3})
        self.fake.reply("/api/web_search", {"results": []})
        self.assertEqual(self.call(server, "search", {"query": "zzz"}), ("No results for: zzz", False))

    def test_fetch(self) -> None:
        page = {"title": "Tides", "content": "x" * 20_000, "links": ["https://other.example/"]}
        self.fake.reply("/api/web_fetch", page)
        text, failed = self.call(self.start(), "fetch", {"url": "https://tides.example/today"})
        self.assertFalse(failed)
        self.assertEqual(self.fake.requests[0]["body"], {"url": "https://tides.example/today"})
        self.assertEqual(self.fake.requests[0]["authorization"], f"Bearer {KEY}")
        self.assertTrue(text.startswith("Title: Tides\nAddress: https://tides.example/today\n\nxxx"))
        self.assertTrue(text.endswith("[cut to 8,000 characters]"))
        self.assertNotIn("other.example", text)

    def test_wrong_inputs_send_nothing(self) -> None:
        server = self.start()
        cases = [("search", {}), ("search", {"query": "  "}), ("search", {"query": "x" * 301}),
                 ("search", {"query": "a", "max_results": 9}), ("search", {"query": "a", "max_results": True}),
                 ("fetch", {}), ("fetch", {"url": "file:///C:/secret.txt"}), ("fetch", {"url": "tides.example"}),
                 ("fetch", {"url": "https://a b.example/"}), ("fetch", {"url": "http://[::1"})]
        for tool, arguments in cases:
            with self.subTest(arguments):
                text, failed = self.call(server, tool, arguments)
                self.assertTrue(failed)
                self.assertTrue(text.startswith("Give "), text)
        self.assertEqual(self.fake.requests, [])

    def test_errors_are_plain(self) -> None:
        server = self.start()
        cases = [(401, {"error": "no"}, "Ollama refused the key (error 401). Check the key in OLLAMA_API_KEY."),
                 (429, {"error": "slow down"}, "too many requests (error 429). Wait a minute"),
                 (500, {"error": f"boom {KEY}"}, "Ollama returned error 500: boom [key]"),
                 (500, b"<html>", "Ollama returned error 500: no details"),
                 (200, b"<html>", "Ollama sent a reply that the search server cannot read.")]
        for status, body, message in cases:
            with self.subTest(status):
                self.fake.reply("/api/web_search", body, status)
                text, failed = self.call(server, "search", {"query": "tides"})
                self.assertTrue(failed)
                self.assertIn(message, text)

    def test_redirect_is_never_followed(self) -> None:
        self.fake.reply("/api/web_fetch", b"", 302, Location="https://elsewhere.example/api/web_fetch")
        text, failed = self.call(self.start(), "fetch", {"url": "https://tides.example/"})
        self.assertTrue(failed)
        self.assertIn("redirect (error 302). The search server never follows a redirect.", text)
        self.assertEqual(len(self.fake.requests), 1)

    def test_no_key_or_a_bad_key_sends_nothing(self) -> None:
        text, failed = self.call(self.start(key=None), "search", {"query": "tides"})
        self.assertEqual((text, failed), (search_server.NO_KEY, True))
        text, failed = self.call(self.start(key="two words"), "search", {"query": "tides"})
        self.assertIn("has spaces or other characters", text)
        self.assertEqual(self.fake.requests, [])

    def test_unreachable_api(self) -> None:
        text, failed = self.call(self.start(url=f"http://127.0.0.1:{closed_port()}"), "search", {"query": "tides"})
        self.assertTrue(failed)
        self.assertTrue(text.startswith("The search server could not reach ollama.com: "), text)

    def test_test_variable_accepts_only_this_computer(self) -> None:
        def target(url: str) -> tuple[str, str, int]:
            with mock.patch.dict(os.environ, {search_server.TEST_VARIABLE: url}):
                connection = search_server.api_connection()  # this opens no connection yet
            return type(connection).__name__, connection.host, connection.port

        self.assertEqual(target(""), ("HTTPSConnection", "ollama.com", 443))  # the normal case
        self.assertEqual(target("http://127.0.0.1:8123"), ("HTTPConnection", "127.0.0.1", 8123))
        for url in ["http://example.com:80", "https://127.0.0.1:8123", "http://localhost:8123", "http://127.0.0.1"]:
            with self.subTest(url), mock.patch.dict(os.environ, {search_server.TEST_VARIABLE: url}):
                with self.assertRaisesRegex(search_server.ToolFailure, "only name a fake on this computer"):
                    search_server.api_connection()

    def test_time_and_size_limits(self) -> None:
        env = {search_server.KEY_VARIABLE: KEY, search_server.TEST_VARIABLE: self.fake.url}
        self.fake.reply("/api/web_search", {"results": [], "padding": "x" * 5_000})
        with mock.patch.dict(os.environ, env), mock.patch.object(search_server, "RESPONSE_LIMIT", 1_000):
            with self.assertRaisesRegex(search_server.ToolFailure, "more than 1,000 bytes"):
                search_server.post("/api/web_search", {"query": "tides"})
        self.fake.delay = 2.0
        start = time.monotonic()
        with mock.patch.dict(os.environ, env), mock.patch.object(search_server, "TIME_LIMIT", 0.5):
            with self.assertRaisesRegex(search_server.ToolFailure, "did not answer within 0.5 seconds"):
                search_server.post("/api/web_search", {"query": "tides"})
        self.assertLess(time.monotonic() - start, 1.8)


if __name__ == "__main__":
    unittest.main()
