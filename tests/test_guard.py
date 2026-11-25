"""Tests for korvin.guard: the loopback check and the connection guard.

Note: an audit hook cannot be removed, so after these tests the guard
stays on for the rest of the test run. The other tests only use 127.0.0.1.
"""

import socket
import unittest

from fake_model import FakeModel
from korvin import config, guard, mcp
from korvin.config import Provider
from korvin.door import ModelDoor, Piece
from test_mcp import LEGACY


class LoopbackHostTest(unittest.TestCase):
    def test_table(self) -> None:
        table = {
            "localhost": True,
            "127.0.0.1": True,
            "127.255.255.254": True,
            "::1": True,
            "0.0.0.0": False,
            "192.168.1.5": False,
            "10.0.0.1": False,
            "8.8.8.8": False,
            "::": False,
            "::ffff:127.0.0.1": False,
            "example.com": False,
            "localhost.example.com": False,
            "LOCALHOST": False,
            "127.1": False,
            "": False,
        }
        for host, expected in table.items():
            with self.subTest(host):
                self.assertEqual(guard.is_loopback_host(host), expected)


class InstallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        guard.install()

    def test_outside_connection_blocked(self) -> None:
        # 192.0.2.1 is a documentation address. Without the guard this would time out, not fail at once.
        with self.assertRaisesRegex(PermissionError, "Only this computer is allowed"):
            socket.create_connection(("192.0.2.1", 80), timeout=1)

    def test_loopback_connection_allowed(self) -> None:
        with FakeModel() as fake:
            connection = socket.create_connection(("127.0.0.1", fake.port), timeout=5)
            connection.close()

    def test_install_twice_is_harmless(self) -> None:
        guard.install()
        guard.install()
        with self.assertRaises(PermissionError):
            socket.create_connection(("192.0.2.1", 80), timeout=1)

    def test_check_event_table(self) -> None:
        refused = [
            ("10.0.0.1", 80),
            ("localhost", 80),
            ("::2", 80, 0, 0),
            ("0.0.0.0", 0),
            ("", 0),
            "/tmp/socket",
            (),
            (2130706433, 80),
        ]
        for event in ["socket.connect", "socket.sendto", "socket.bind"]:
            for address in refused:
                with self.subTest(event=event, address=address), self.assertRaises(PermissionError):
                    guard._check_event(event, (None, address))
            for address in [("127.0.0.1", 80), ("127.0.0.1", 0), ("::1", 80, 0, 0)]:
                with self.subTest(event=event, address=address):
                    self.assertIsNone(guard._check_event(event, (None, address)))

    def test_lookup_table(self) -> None:
        allowed = ["localhost", "127.0.0.1", "::1", b"localhost", b"127.0.0.1", None, "", b""]
        refused = ["example.com", "192.0.2.1", "0.0.0.0", "LOCALHOST", "127.1", b"example.com", b"local\xffhost", 5]
        for host in allowed:
            with self.subTest(host):
                self.assertIsNone(guard._check_event("socket.getaddrinfo", (host, 80, 0, 0, 0)))
        for host in refused:
            with self.subTest(host), self.assertRaisesRegex(PermissionError, "name lookup"):
                guard._check_event("socket.getaddrinfo", (host, 80, 0, 0, 0))

    def test_name_lookup_blocked(self) -> None:
        # AI_NUMERICHOST and an IP address mean that no lookup leaves this computer, even without the guard.
        with self.assertRaisesRegex(PermissionError, "Korvin blocked a name lookup"):
            socket.getaddrinfo("example.com", 80, flags=socket.AI_NUMERICHOST)
        with self.assertRaisesRegex(PermissionError, "Korvin blocked a name lookup"):
            socket.getaddrinfo(b"192.0.2.1", 80)
        self.assertTrue(socket.getaddrinfo("127.0.0.1", 80))
        self.assertTrue(socket.getaddrinfo(None, 80))

    def test_sendto_blocked(self) -> None:
        # Data sent to 0.0.0.0 cannot leave this computer, even without the guard.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            with self.assertRaisesRegex(PermissionError, "Korvin blocked sending data"):
                sock.sendto(b"x", ("0.0.0.0", 9))
            self.assertEqual(sock.sendto(b"x", sock.getsockname()), 1)

    def test_connect_blocked_without_lookup(self) -> None:
        # A plain socket skips the name lookup, so only the connect check stops it.
        with socket.socket() as sock, self.assertRaisesRegex(PermissionError, "Korvin blocked a connection"):
            sock.connect(("0.0.0.0", 9))

    def test_bind_outside_loopback_blocked(self) -> None:
        for host in ["0.0.0.0", ""]:
            with self.subTest(host), socket.socket() as sock:
                with self.assertRaisesRegex(PermissionError, "Korvin blocked opening a socket"):
                    sock.bind((host, 0))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.assertNotEqual(sock.getsockname()[1], 0)

    def test_fake_server_and_door_work(self) -> None:
        with FakeModel(thinking=("hmm",), pieces=("Hi",)) as fake:
            door = ModelDoor(Provider(name="local", base_url=fake.base_url, remote=False), timeout=10)
            self.assertEqual(door.list_models(), ["fake-model"])
            pieces = list(door.stream_chat("fake-model", []))
        self.assertEqual(pieces, [Piece("thinking", "hmm"), Piece("answer", "Hi")])

    def test_other_events_ignored(self) -> None:
        self.assertIsNone(guard._check_event("open", ("file.txt", "r", 0)))
        self.assertIsNone(guard._check_event("subprocess.Popen", ("python", ["python"], None, None)))

    def test_tool_server_starts_with_the_guard_on(self) -> None:
        # The guard is on for this whole test class. Starting a tool server, a child process, still works.
        server = mcp.Server(LEGACY, config.child_environment([]))
        try:
            server.start()
            self.assertEqual(server.call("echo", {"text": "guarded"}), ("guarded", False))
        finally:
            server.close()

    def test_korvin_stays_local_while_a_server_runs(self) -> None:
        # A running child process does not open a door for Korvin itself.
        server = mcp.Server(LEGACY, config.child_environment([]))
        try:
            server.start()
            with self.assertRaisesRegex(PermissionError, "Only this computer is allowed"):
                socket.create_connection(("192.0.2.1", 80), timeout=1)
            with socket.socket() as sock, self.assertRaisesRegex(PermissionError, "Korvin blocked a connection"):
                sock.connect(("0.0.0.0", 9))
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
