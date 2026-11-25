"""Tests for korvin.door: talking to the model service."""

import json
import socket
import unittest

from fake_model import FakeModel, answer, tool_call
from korvin.config import Provider
from korvin.door import LINE_LIMIT, DoorError, ModelDoor, Piece, ToolCall, ToolsNotSupported, Usage
from korvin.tools import SCHEMAS

TIMEOUT_MESSAGE = "did not answer in time. The first answer after the service starts can be slow"


def door_for(base_url: str, timeout: float = 10, start_timeout: float = 10) -> ModelDoor:
    provider = Provider(name="local", base_url=base_url, remote=False)
    return ModelDoor(provider, timeout=timeout, start_timeout=start_timeout)


def answers(*texts: str) -> list[Piece]:
    return [Piece("answer", text) for text in texts]


def one_line_stream(delta: dict) -> bytes:
    """Return a stream with one event that holds this delta, then the end."""
    return b"data: " + json.dumps({"choices": [{"delta": delta}]}).encode("utf-8") + b"\n\ndata: [DONE]\n\n"


def closed_port() -> int:
    """Return a port on 127.0.0.1 that nothing listens on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DoorTest(unittest.TestCase):
    def test_list_models(self) -> None:
        with FakeModel(models=("a", "b")) as fake:
            self.assertEqual(door_for(fake.base_url).list_models(), ["a", "b"])

    def test_list_models_null_means_none(self) -> None:
        with FakeModel(models=None) as fake:
            self.assertEqual(door_for(fake.base_url).list_models(), [])

    def test_stream_chat(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        with FakeModel(pieces=("One", " two", " three")) as fake:
            pieces = list(door_for(fake.base_url).stream_chat("fake-model", messages))
        self.assertEqual(pieces, answers("One", " two", " three"))
        usage = {"stream_options": {"include_usage": True}}
        sampling = {"temperature": 0.6, "presence_penalty": 0.0}
        self.assertEqual(fake.requests,
                         [{"model": "fake-model", "messages": messages, "stream": True, **usage, **sampling}])

    def test_sampling_sent_with_tools_too(self) -> None:
        # D-023: a temperature of 0.6 and no presence penalty made tool work more reliable than the stored values.
        with FakeModel(pieces=("Hi",)) as fake:
            list(door_for(fake.base_url).stream_chat("fake-model", [], SCHEMAS))
        self.assertEqual((fake.requests[0]["temperature"], fake.requests[0]["presence_penalty"]), (0.6, 0.0))
        self.assertEqual(fake.requests[0]["tools"], SCHEMAS)

    def test_non_ascii_round_trip(self) -> None:
        messages = [{"role": "user", "content": "café ñ 日本"}]
        with FakeModel(pieces=("café ", "ñ ", "日本")) as fake:
            pieces = list(door_for(fake.base_url).stream_chat("fake-model", messages))
        self.assertEqual("".join(piece.text for piece in pieces), "café ñ 日本")
        self.assertEqual(fake.requests[0]["messages"], messages)

    def test_thinking_kept_apart_from_answer(self) -> None:
        with FakeModel(thinking=("Let me", " think"), pieces=("Hi",)) as fake:
            pieces = list(door_for(fake.base_url).stream_chat("fake-model", []))
        self.assertEqual(pieces, [Piece("thinking", "Let me"), Piece("thinking", " think"), Piece("answer", "Hi")])

    def test_thinking_and_answer_in_one_line(self) -> None:
        with FakeModel(raw_stream=one_line_stream({"reasoning": "hmm", "content": "Hi"})) as fake:
            pieces = list(door_for(fake.base_url).stream_chat("fake-model", []))
        self.assertEqual(pieces, [Piece("thinking", "hmm"), Piece("answer", "Hi")])

    def test_null_fields_give_no_pieces(self) -> None:
        with FakeModel(raw_stream=one_line_stream({"reasoning": None, "content": None})) as fake:
            self.assertEqual(list(door_for(fake.base_url).stream_chat("fake-model", [])), [])

    def test_slow_start_uses_the_longer_timeout(self) -> None:
        with FakeModel(start_delay=1.5) as fake:
            pieces = list(door_for(fake.base_url, timeout=0.5, start_timeout=10).stream_chat("fake-model", []))
        self.assertEqual(pieces, answers("Hello", " there"))

    def test_start_too_slow(self) -> None:
        with FakeModel(start_delay=1.5) as fake:
            with self.assertRaisesRegex(DoorError, TIMEOUT_MESSAGE):
                list(door_for(fake.base_url, timeout=10, start_timeout=0.5).stream_chat("fake-model", []))

    def test_pieces_too_slow(self) -> None:
        with FakeModel(line_delay=1.5) as fake:
            with self.assertRaisesRegex(DoorError, TIMEOUT_MESSAGE):
                list(door_for(fake.base_url, timeout=0.5, start_timeout=10).stream_chat("fake-model", []))

    def test_line_size_limit(self) -> None:
        prefix = b'data: {"choices": [{"delta": {"content": "'
        suffix = b'"}}]}\n'
        fits = prefix + b"x" * (LINE_LIMIT - len(prefix) - len(suffix)) + suffix
        with FakeModel(raw_stream=fits + b"\ndata: [DONE]\n\n") as fake:
            pieces = list(door_for(fake.base_url).stream_chat("fake-model", []))
        self.assertEqual(len(fits), LINE_LIMIT)
        self.assertEqual(len(pieces[0].text), LINE_LIMIT - len(prefix) - len(suffix))
        too_long = prefix + b"x" * (LINE_LIMIT - len(prefix) - len(suffix) + 1) + suffix
        with FakeModel(raw_stream=too_long + b"\ndata: [DONE]\n\n") as fake:
            with self.assertRaisesRegex(DoorError, "line that is too long"):
                list(door_for(fake.base_url).stream_chat("fake-model", []))

    def test_http_error(self) -> None:
        with FakeModel(failures=1) as fake:
            with self.assertRaisesRegex(DoorError, "error 500: fake failure"):
                list(door_for(fake.base_url).stream_chat("fake-model", []))

    def test_redirect_refused(self) -> None:
        with FakeModel(failures=1, fail_status=302) as fake:
            with self.assertRaisesRegex(DoorError, "does not follow redirects"):
                list(door_for(fake.base_url).stream_chat("fake-model", []))

    def test_connection_refused(self) -> None:
        door = door_for(f"http://127.0.0.1:{closed_port()}/v1")
        with self.assertRaisesRegex(DoorError, "Is Ollama running\\?"):
            door.list_models()
        with self.assertRaisesRegex(DoorError, "Is Ollama running\\?"):
            list(door.stream_chat("fake-model", []))

    def test_malformed_stream(self) -> None:
        streams = [
            b"data: {not json}\n\n",
            b"hello\n\ndata: [DONE]\n\n",
            b'data: {"choices": []}\n\ndata: [DONE]\n\n',
            b'data: {"choices": [{"delta": {"content": 5}}]}\n\ndata: [DONE]\n\n',
            b'data: {"choices": [{"delta": {"content": "", "reasoning": 5}}]}\n\ndata: [DONE]\n\n',
            b'data: {"choices": [{"delta": {"reasoning": ["a"]}}]}\n\ndata: [DONE]\n\n',
            b'data: {"choices": [{"delta": "text"}]}\n\ndata: [DONE]\n\n',
            b'data: {"choices": [{"delta": {"content": "cut short"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": "\xff"}}]}\n\ndata: [DONE]\n\n',
        ]
        for raw in streams:
            with self.subTest(raw), FakeModel(raw_stream=raw) as fake:
                with self.assertRaises(DoorError):
                    list(door_for(fake.base_url).stream_chat("fake-model", []))

    def test_error_inside_stream(self) -> None:
        raw = b'data: {"error": {"message": "model crashed"}}\n\n'
        with FakeModel(raw_stream=raw) as fake:
            with self.assertRaisesRegex(DoorError, "model crashed"):
                list(door_for(fake.base_url).stream_chat("fake-model", []))

    def stream(self, script: list, tools: list[dict] | None = SCHEMAS) -> tuple[list, FakeModel]:
        """Return what stream_chat yields for one scripted reply, and the fake model."""
        with FakeModel(script=script) as fake:
            items = list(door_for(fake.base_url).stream_chat("fake-model", [], tools))
        return items, fake

    def test_tools_sent_only_when_given(self) -> None:
        _items, fake = self.stream([answer("Hi")])
        self.assertEqual(fake.requests[0]["tools"], SCHEMAS)
        _items, fake = self.stream([answer("Hi")], tools=None)
        self.assertNotIn("tools", fake.requests[0])

    def test_tool_call_pieces_joined(self) -> None:
        for pieces in [1, 2, 4, 25]:
            with self.subTest(pieces=pieces):
                items, _fake = self.stream([tool_call("read_file", '{"path": "plan.txt"}', pieces=pieces)])
                self.assertEqual(items, [ToolCall("call_0", "read_file", '{"path": "plan.txt"}')])

    def test_tool_call_id_kept(self) -> None:
        items, _fake = self.stream([tool_call("find_note", "{}", call_id="call_abc", pieces=3)])
        self.assertEqual(items, [ToolCall("call_abc", "find_note", "{}")])

    def test_text_then_tool_calls(self) -> None:
        deltas = answer("Let me look.") + tool_call("list_folder", '{"path": "."}')
        items, _fake = self.stream([deltas])
        self.assertEqual(items, [Piece("answer", "Let me look."), ToolCall("call_0", "list_folder", '{"path": "."}')])

    def test_two_calls_in_index_order(self) -> None:
        # The parts of two calls arrive mixed, and the second call starts first.
        second = tool_call("find_note", '{"query": "a"}', index=1, pieces=2)
        first = tool_call("read_file", "{}", index=0, pieces=2)
        items, _fake = self.stream([[second[0], first[0], second[1], first[1]]])
        expected = [ToolCall("call_0", "read_file", "{}"), ToolCall("call_1", "find_note", '{"query": "a"}')]
        self.assertEqual(items, expected)
        # Two whole calls can also arrive in one event, as Ollama can send them.
        whole = [tool_call("find_note", "{}", index=1)[0], tool_call("read_file", "{}")[0]]
        parts = [delta["tool_calls"][0] for delta in whole]
        items, _fake = self.stream([[{"content": "", "tool_calls": parts}]])
        self.assertEqual([item.name for item in items], ["read_file", "find_note"])

    def test_malformed_tool_calls(self) -> None:
        good = {"index": 0, "id": "a", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
        bad_parts = [
            "not a list",
            ["not an object"],
            [{**good, "index": None}],
            [{key: value for key, value in good.items() if key != "index"}],
            [{**good, "index": "0"}],
            [{**good, "index": True}],
            [{**good, "index": -1}],
            [{**good, "type": "code"}],
            [{**good, "id": 5}],
            [{**good, "function": "read_file"}],
            [{**good, "function": {"name": 5}}],
            [{**good, "function": {"name": "read_file", "arguments": {"path": "x"}}}],
            [{**good, "function": {"arguments": "{}"}}],  # a call with no name
            [good, {**good, "id": "b"}],  # two ids for one call
        ]
        for parts in bad_parts:
            with self.subTest(parts=parts), self.assertRaises(DoorError):
                self.stream([[{"content": "", "tool_calls": parts}]])

    def test_null_tool_calls_ignored(self) -> None:
        items, _fake = self.stream([[{"content": "Hi", "tool_calls": None}]])
        self.assertEqual(items, answers("Hi"))

    def test_tools_not_supported(self) -> None:
        with FakeModel(refuse_tools=True) as fake:
            door = door_for(fake.base_url)
            with self.assertRaisesRegex(ToolsNotSupported, "This model cannot use tools."):
                list(door.stream_chat("fake-model", [], SCHEMAS))
            self.assertEqual(list(door.stream_chat("fake-model", [])), answers("Hello", " there"))
        self.assertTrue(issubclass(ToolsNotSupported, DoorError))

    def test_other_400_is_a_plain_door_error(self) -> None:
        with FakeModel(failures=1, fail_status=400) as fake:
            with self.assertRaisesRegex(DoorError, "error 400: fake failure") as caught:
                list(door_for(fake.base_url).stream_chat("fake-model", [], SCHEMAS))
        self.assertNotIsInstance(caught.exception, ToolsNotSupported)

    def test_usage_comes_last(self) -> None:
        with FakeModel(script=[answer("Hi") + tool_call("read_file", "{}")], usage=True) as fake:
            items = list(door_for(fake.base_url).stream_chat("fake-model", [{"role": "user", "content": "x"}]))
        tokens = len('[{"role": "user", "content": "x"}]')  # the fake counts one token for each character
        self.assertEqual(items[1:], [ToolCall("call_0", "read_file", "{}"), Usage(tokens)])
        self.assertEqual(fake.requests[0]["stream_options"], {"include_usage": True})

    def test_bad_usage_refused(self) -> None:
        for usage in ['{"prompt_tokens": "5"}', '{"prompt_tokens": -1}', '{"prompt_tokens": true}', "{}"]:
            raw = b'data: {"choices": [], "usage": ' + usage.encode() + b"}\n\ndata: [DONE]\n\n"
            with self.subTest(usage), FakeModel(raw_stream=raw) as fake, self.assertRaises(DoorError):
                list(door_for(fake.base_url).stream_chat("fake-model", []))

    def test_context_size(self) -> None:
        with FakeModel(context=65_536) as fake:
            door = door_for(fake.base_url)
            self.assertEqual(door.context_size("fake-model"), 65_536)
            self.assertIsNone(door.context_size("other-model"))
        with FakeModel(context=None) as fake:
            self.assertIsNone(door_for(fake.base_url).context_size("fake-model"))
        self.assertIsNone(door_for(f"http://127.0.0.1:{closed_port()}/v1").context_size("fake-model"))

    def test_gpu_share(self) -> None:
        with FakeModel(gpu=0.5) as fake:
            door = door_for(fake.base_url)
            self.assertEqual(door.gpu_share("fake-model"), 0.5)
            self.assertIsNone(door.gpu_share("other-model"))
        with FakeModel() as fake:
            self.assertIsNone(door_for(fake.base_url).gpu_share("fake-model"))  # no sizes in the reply

    def test_native_model_api(self) -> None:
        facts = {"capabilities": ["tools"], "parameters": "num_ctx 65536"}
        with FakeModel(models=("a", "b"), shows={"a": facts}) as fake:
            door = door_for(fake.base_url)
            self.assertEqual([entry["name"] for entry in door.installed_models()], ["a", "b"])
            self.assertEqual(door.model_facts("a"), facts)
            with self.assertRaisesRegex(DoorError, "error 404"):
                door.model_facts("b")
            door.create_copy("c", "a", {"num_ctx": 65_536})
        self.assertEqual(fake.requests[-1], {"model": "c", "from": "a", "parameters": {"num_ctx": 65_536}, "stream": False})
        with FakeModel(models=None) as fake:
            self.assertEqual(door_for(fake.base_url).installed_models(), [])
        with FakeModel(create_status=500) as fake, self.assertRaisesRegex(DoorError, "error 500"):
            door_for(fake.base_url).create_copy("c", "a", {})

    def test_non_loopback_provider_refused_before_connecting(self) -> None:
        for url in ["http://example.com/v1", "https://127.0.0.1/v1"]:
            with self.subTest(url), self.assertRaisesRegex(DoorError, "not allowed|Only this computer"):
                door_for(url).list_models()
        remote = ModelDoor(Provider(name="cloud", base_url="http://127.0.0.1/v1", remote=True))
        with self.assertRaises(DoorError):
            remote.list_models()


if __name__ == "__main__":
    unittest.main()
