"""Grade one record, and build the result entry that the JSON file keeps.

A live run and a rescore use the same functions, so a rescore gives the same verdict for the same record.
"""

from dataclasses import asdict

from evals.decision import judge_reply, reply_from_dict
from evals.labels import label
from evals.runner import judge, trial_from_dict


def grade(item, record) -> dict:
    """Return the verdict, the reason, the hidden-order outcome, the observations, and the failure label."""
    if item.target == "decision":
        passed, reason = judge_reply(item, record)
        observed = item.observe(record) if item.observe else None
        return {"passed": passed, "reason": reason, "injection": None, "observed": observed, "label": None}
    passed, reason = judge(item, record)
    injection = None
    if item.injection:
        injection = f"did not finish ({record.failure})" if record.failure else item.injection(record)
    observed = item.observe(record) if item.observe else None
    failure_label = None if passed else label(item, record, reason, injection)
    return {"passed": passed, "reason": reason, "injection": injection, "observed": observed, "label": failure_label}


def entry(item, number: int, record) -> dict:
    """Return the result entry of one trial: what the task was, the grade, and the full record."""
    return {
        "task": item.id, "kind": item.kind, "family": item.family_number, "target": item.target,
        "steps": item.steps, "trial": number, **grade(item, record), "seconds": record.seconds,
        "user_lines": list(item.user_lines), "gate": getattr(item, "gate", None), "info": item.info,
        "record": asdict(record),
    }


def rebuild(result: dict):
    """Return the record object of a saved result entry."""
    if result.get("target") == "decision":
        return reply_from_dict(result["record"])
    return trial_from_dict(result["record"])
