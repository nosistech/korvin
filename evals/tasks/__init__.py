"""Every eval task and decision case, one module for each family.

core: the first 29 whole tasks. decisions: single-decision cases. honesty: use of results and honesty.
impossible: impossible requests as whole tasks. context: long context and overflow.
attacks: the hidden-order matrix. conversations: many turns. wording: rewordings and Spanish.
tool_servers: a local tool server, through Korvin's real MCP client.
finding: facts spread over many files, and notes found by words that the note does not hold.
"""

from evals.tasks import (
    attacks, context, conversations, core, decisions, finding, honesty, impossible, tool_servers, wording,
)

TASKS = (core.TASKS + honesty.TASKS + impossible.TASKS + conversations.TASKS + wording.TASKS + attacks.TASKS
         + context.TASKS + tool_servers.TASKS + finding.TASKS)
CASES = decisions.CASES
ALL = TASKS + CASES
_BY_ID = {item.id: item for item in ALL}
if len(_BY_ID) != len(ALL):
    raise ValueError("Two eval tasks have the same id.")


def by_id(task_id: str):
    """Return the task or decision case with this id."""
    return _BY_ID[task_id]


def find(task_id: str):
    """Return the task or decision case with this id, or None if it does not exist any more."""
    return _BY_ID.get(task_id)
