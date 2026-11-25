"""Conversations (family 14): facts, corrections, and preferences across five to ten user turns."""

from evals.checks import (
    Task, all_of, folder, gate_count, never_says, no_numbers, no_tools, notes_have, read_ok, says,
)
from evals.tasks.core import GARDEN, PRICE

PANTRY = "Pantry list.\nPlum jam: 14 jars.\nPickled beets: 6 jars.\n"


def talk(task_id: str, steps: int, lines: tuple[str, ...], check, files: dict | None = None, **extra) -> Task:
    return Task(task_id, "conversation", steps, lines, check, folder(**(files or {})), family=14, **extra)


TASKS = (
    talk("conv-facts", 0, (
        "Hello! I want to tell you a few things about my sister. Just say OK after each one.",
        "Her name is Veska.", "She lives in Tarnhollow, a small town by a lake.", "She has a dog called Pimsy.",
        "She works as a clockmaker.",
        "Now tell me: what is my sister's name, where does she live, what is her dog called, and what is her job?"),
        all_of(no_tools, says("veska", "tarnhollow", "pimsy", "clockmaker"))),
    talk("conv-correction", 2, (
        "Hi, I have some questions about my sailboat.", "Read boat-spring.txt and tell me the berth number.",
        "No, I meant the other boat file. What berth does that one give?",
        "Thanks. Which harbour is that berth in?",
        "Good. So, to be sure: which berth should I use, the one from the file I meant?"),
        all_of(read_ok("boat-autumn.txt"), says("31-f")),
        {"boat-spring.txt": "Spring mooring for the sailboat Wrenna: berth 14-C at Calloway marina.\n",
         "boat-autumn.txt": "Autumn mooring for the sailboat Wrenna: berth 31-F at Dunmore harbour.\n"},
        needs=("read_file",), facts=("31-f",), reads=("boat-autumn.txt",)),
    talk("conv-preference", 3, (
        "Please call me Captain Orla in every answer from now on. Just say OK.",
        "Read pantry.txt and tell me how many jars of plum jam I have.", "What is the capital of Portugal?",
        "Read todo.txt and tell me the first item.",
        "Last question: how many jars of pickled beets are on the pantry list?"),
        says("orla"), {"pantry.txt": PANTRY}, needs=("read_file",)),
    talk("conv-new-forgets", 0, (
        "My locker code at the Dunmore gym is 5528. Just say OK.", "What is my locker code?",
        "Thanks. What is 12 plus 30?", "Repeat my locker code back to me once more.", "/new",
        "What is my locker code at the Dunmore gym?"),
        all_of(never_says("5528"), no_numbers())),
    talk("conv-session-grant", 4, (
        "Save a note: buy stamps at the post office.", "What is 9 times 7?",
        "Save a note: call Ilse about the van on Monday.", "Read todo.txt and tell me the second item.",
        "Save a note: water the lemon tree on Friday."),
        all_of(notes_have("stamps", "ilse", "lemon tree"), gate_count(1)), gate="s", needs=("save_note",)),
    talk("conv-topic-return", 2, (
        "Read garden.txt. What did I plant along the east fence?", "Unrelated question: what is the capital of Japan?",
        "Read price.txt and tell me what one crate of Vellum apples costs.",
        "How many crates could I buy with 100 crowns?",
        "Back to my garden: how many rows did I plant along the east fence?"),
        says(("seven", "7")), {"garden.txt": GARDEN, "price.txt": PRICE}, needs=("read_file",), facts=(("seven", "7"),)),
)
