"""Numbers that the reports share: pass rates, the every-time rate pass^k, medians, and the cost of a trial."""

from collections import defaultdict
from math import comb
from statistics import median

from evals.checks import FAMILIES, KIND_FAMILY

KS = (1, 3, 5)


def family_of(result: dict) -> int:
    """Return the family number of a result. Old result files have no family, so the kind decides."""
    return result.get("family") or KIND_FAMILY.get(result["kind"], 1)


def family_name(number: int) -> str:
    return f"{number}. {FAMILIES.get(number, 'Other')}"


def pass_hat(passed: int, trials: int, k: int) -> float | None:
    """Return the chance that k trials, drawn from these trials without replacement, all pass.

    This is the unbiased estimate of pass^k from tau-bench. It needs at least k trials.
    """
    return comb(passed, k) / comb(trials, k) if k <= trials else None


def by_task(results: list[dict]) -> dict[str, tuple[int, int]]:
    """Return the passes and the trials of each task, in the order of the results."""
    counts: dict[str, list[int]] = {}
    for r in results:
        pair = counts.setdefault(r["task"], [0, 0])
        pair[0] += r["passed"]
        pair[1] += 1
    return {task: (p, n) for task, (p, n) in counts.items()}


def reliability(results: list[dict]) -> dict[int, float | None]:
    """Return pass^k for each k: the mean over the tasks that have at least k trials. None if no task has."""
    counts = list(by_task(results).values())
    rates = {}
    for k in KS:
        values = [pass_hat(p, n, k) for p, n in counts if n >= k]
        rates[k] = sum(values) / len(values) if values else None
    return rates


def group(results: list[dict], key) -> dict:
    """Return the results grouped by a key function, in the order the keys first appear."""
    groups: dict = defaultdict(list)
    for r in results:
        groups[key(r)].append(r)
    return dict(groups)


def middle(values: list) -> float | None:
    """Return the median of the numbers that are not None, or None."""
    values = [v for v in values if v is not None]
    return median(values) if values else None


def cost(result: dict) -> dict | None:
    """Return the cost of one whole-task trial, or None for a decision case."""
    if result.get("target", "task") != "task":
        return None
    record = result["record"]
    requests = record.get("requests") or []
    return {
        "requests": record["model_requests"], "actions": len(record["actions"]), "minimal": result["steps"],
        "seconds": result["seconds"],
        "thinking": sum(r.get("thinking", 0) for r in requests) if requests else None,
        "read_questions": record.get("read_questions", 0),
    }


def over_budget(c: dict) -> bool:
    """Return True if a trial used more than twice the smallest number of tool actions.

    A task that needs no action is over budget with any action at all.
    """
    return c["actions"] > 2 * c["minimal"]


def percent(value: float | None) -> str:
    return "-" if value is None else f"{round(100 * value)}%"


def rate(passed: int, total: int) -> str:
    return f"{round(100 * passed / total)}%" if total else "-"
