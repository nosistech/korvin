"""Tests for the eval families 19 and 20: finding facts in many files, and recall of notes. No real model."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from korvin.door import ModelDoor, Piece, ToolCall


def run_offline(task_id: str, replies: list[list]) -> tuple[dict, object, list[list[dict]]]:
    """Run one trial of a task with a scripted model, through the real eval runner, and grade it."""
    from evals import runner
    from evals.grading import grade
    from evals.tasks import by_id

    task, seen, replies = by_id(task_id), [], list(replies)

    def stream_chat(_door, _model, messages, _tools=None):
        seen.append(list(messages))
        yield from replies.pop(0)

    root = Path(tempfile.mkdtemp(prefix="korvin-test-finding-"))
    try:
        with mock.patch.object(ModelDoor, "stream_chat", stream_chat), \
                mock.patch.object(ModelDoor, "context_size", return_value=65_536), \
                mock.patch.object(ModelDoor, "gpu_share", return_value=1.0):
            runner.build_fixture(task, root, "fake-model")
            runner.child_main(task.id, str(root))
            trial = runner.read_trial(task, 1, root, 0.0, None, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return grade(task, trial), trial, seen


def call(name: str, **arguments: str) -> ToolCall:
    return ToolCall(f"c_{name}", name, json.dumps(arguments))


class FindingTaskTest(unittest.TestCase):
    def test_fixtures(self) -> None:
        from evals.tasks import by_id, finding

        for task in finding.SEARCH_TASKS:
            with self.subTest(task.id):
                self.assertTrue(9 <= len(task.all_files()) <= 11)
                for fact in task.facts:
                    self.assertEqual(sum(fact in text.casefold() for text in task.all_files().values()), 1)
        self.assertFalse(any("piano" in text for text in by_id("search-none").all_files().values()))
        for task_id, words in [("recall-bike", ("bicycle", "extra")), ("recall-optician", ("optician", "appointment"))]:
            save_line = by_id(task_id).user_lines[0].casefold()
            self.assertFalse(any(word in save_line for word in words))

    def test_search_none_and_recall(self) -> None:
        replies = [[call("list_folder", path=".")], [Piece("answer", "None of your files mentions a piano.")]]
        self.assertTrue(run_offline("search-none", replies)[0]["passed"])
        save_call = call("save_note", text="Dr. Halloran moved my eye exam to Friday at 10:30.")
        replies = [[save_call], [Piece("answer", "Saved.")], [call("find_note", query="optician")],
                   [Piece("answer", "I found no note about that.")]]
        result, _trial, _seen = run_offline("recall-optician", replies)
        self.assertEqual(result["reason"], 'answer lacks "10:30"')
        replies = [[save_call], [Piece("answer", "Saved.")], [call("find_note", query="eye exam")],
                   [Piece("answer", "Friday at 10:30.")]]
        result, _trial, seen = run_offline("recall-optician", replies)
        self.assertTrue(result["passed"], result["reason"])
        self.assertIn("10:30", seen[3][-1]["content"])


if __name__ == "__main__":
    unittest.main()
