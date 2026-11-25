"""Work with saved runs, with no model: grade again, compare two runs, and check the checks against a person.

- rescore: apply the current checks and labels to the records of a saved run.
- compare: put two runs side by side, and warn when they are not comparable.
- label_sample and agreement: a person marks a sample of trials, and the program counts the agreement.
"""

import json
import random
import re
from datetime import datetime
from pathlib import Path

from evals.grading import entry, rebuild
from evals.metrics import KS, by_task, family_name, family_of, group, pass_hat, percent, rate, reliability
from evals.report import table, write_results
from evals.tasks import find

COMPARABLE = ("model", "digest", "ollama_version", "korvin_version", "context_length", "prompt_fingerprint",
              "schemas_fingerprint", "task_fingerprint", "code_fingerprint")
MARK = re.compile(r"^Your mark \(P or F\):[ \t]*([PFpf])?", re.MULTILINE)
VERDICT = re.compile(r"^- Item (\d+): (pass|FAIL)", re.MULTILINE)
SHOW_LIMIT = 700  # the most characters of one file or answer that a labelling sheet shows


def load(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(Path(path).read_text("utf-8"))
    return data["meta"], data["results"]


def rescore(path: Path) -> int:
    """Grade a saved run again with the current checks. Write a new JSON file and report next to it."""
    meta, results = load(path)
    new, changed, missing, reasons = [], [], 0, 0
    for old in results:
        item = find(old["task"])
        if item is None:
            missing += 1
            new.append(old)
            continue
        result = entry(item, old["trial"], rebuild(old))
        new.append(result)
        if result["passed"] != old["passed"]:
            changed.append(f"{old['task']} trial {old['trial']}: {verdict(old)} -> {verdict(result)}")
        reasons += result["reason"] != old["reason"]
    meta = {**meta, "rescored": datetime.now().strftime("%Y-%m-%d %H:%M"), "rescored_from": Path(path).name}
    json_path, report_path = write_results(Path(path).parent, meta, new, "-rescored")
    print(f"Rescored {len(results)} trials. {len(changed)} verdicts changed. {reasons} reasons changed.")
    if missing:
        print(f"{missing} trials belong to tasks that no longer exist. They keep their old verdict.")
    print("\n".join(f"  {line}" for line in changed))
    print(f"Results: {json_path}\nReport:  {report_path}")
    return 0


def verdict(result: dict) -> str:
    return "pass" if result["passed"] else f"FAIL ({result['reason']})"


def compare(path_a: Path, path_b: Path) -> int:
    """Write a side-by-side report of two runs next to the second one, and warn when they differ in setup."""
    (meta_a, results_a), (meta_b, results_b) = load(path_a), load(path_b)
    warnings = []
    for key in COMPARABLE:
        a, b = meta_a.get(key), meta_b.get(key)
        if a is None or b is None:
            which = "either run" if a is None and b is None else ("run A" if a is None else "run B")
            warnings.append(f"{key} is not recorded in {which}. The runs may not be comparable.")
        elif a != b:
            warnings.append(f"The runs differ in {key}: A has {str(a)[:20]}, B has {str(b)[:20]}.")
    for line in warnings:
        print(f"WARNING: {line}")
    lines = ["# Comparison of two eval runs", "", f"- A: {Path(path_a).name}, {meta_a['date']}, {meta_a['model']}",
             f"- B: {Path(path_b).name}, {meta_b['date']}, {meta_b['model']}", ""]
    lines += ["## Warnings", "", *[f"- **{w}**" for w in warnings], ""] if warnings else ["No setup differences.", ""]
    lines += family_table(results_a, results_b) + task_table(results_a, results_b)
    out = Path(path_b).parent / f"compare-{meta_a['stamp']}-vs-{meta_b['stamp']}.md"
    out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"Comparison: {out}")
    return 0


def share(results: list[dict]) -> float | None:
    return sum(r["passed"] for r in results) / len(results) if results else None


def points(a: float | None, b: float | None) -> str:
    return "-" if a is None or b is None else f"{round(100 * (b - a)):+d} points"


def family_table(results_a: list[dict], results_b: list[dict]) -> list[str]:
    families_a, families_b = group(results_a, family_of), group(results_b, family_of)
    rows = []
    for family in sorted(set(families_a) | set(families_b)):
        a, b = families_a.get(family, []), families_b.get(family, [])
        hats_a, hats_b = reliability(a), reliability(b)
        rows.append([family_name(family), percent(share(a)), percent(share(b)), points(share(a), share(b)),
                     *[f"{percent(hats_a[k])} / {percent(hats_b[k])}" for k in KS]])
    head = ["Family", "A pass rate", "B pass rate", "Change", *[f"Every time ({k}) A / B" for k in KS]]
    return ["## By family", "", *table(head, rows)]


def task_table(results_a: list[dict], results_b: list[dict]) -> list[str]:
    counts_a, counts_b = by_task(results_a), by_task(results_b)
    rows = []
    for task in dict.fromkeys([*counts_a, *counts_b]):
        (pa, na), (pb, nb) = counts_a.get(task, (0, 0)), counts_b.get(task, (0, 0))
        hats = f"{percent(pass_hat(pa, na, 3))} / {percent(pass_hat(pb, nb, 3))}"
        rows.append([task, f"{pa}/{na}" if na else "-", f"{pb}/{nb}" if nb else "-",
                     points(pa / na if na else None, pb / nb if nb else None), hats])
    return ["## By task", "", *table(["Task", "A passed", "B passed", "Change", "Every time (3) A / B"], rows)]


def sample(results: list[dict], count: int) -> list[dict]:
    """Return a fixed sample: half passes and half failures, spread over the families in turn."""
    rng = random.Random(1123)
    picked = []
    for passed, want in ((False, count // 2), (True, count - count // 2)):
        pools = [rows[:] for _f, rows in sorted(group([r for r in results if r["passed"] == passed], family_of).items())]
        for pool in pools:
            rng.shuffle(pool)
        while len([p for p in picked if p["passed"] == passed]) < want and any(pools):
            for pool in pools:
                if pool and len([p for p in picked if p["passed"] == passed]) < want:
                    picked.append(pool.pop())
    short = count - len(picked)  # too few failures: fill up with more passes, or the other way round
    rest = [r for r in results if r not in picked]
    rng.shuffle(rest)
    return sorted(picked + rest[:max(short, 0)], key=lambda r: (r["task"], r["trial"]))


def clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= SHOW_LIMIT else text[:SHOW_LIMIT] + f" [... {len(text) - SHOW_LIMIT:,} more characters]"


def item_lines(index: int, result: dict) -> list[str]:
    """Return what a person needs to judge one trial, without the program's verdict."""
    record = result["record"]
    lines = [f"## Item {index}", "", f"Task: {result['task']} (trial {result['trial']}). "
             f"Family: {family_name(family_of(result))}.", ""]
    task = find(result["task"])
    if result.get("target") == "decision":
        lines += ["Conversation before the reply:", "", "```"]
        lines += [f"[{m['role']}] {clip(str(m.get('content') or ''))}" for m in record["messages"][1:]] + ["```", ""]
        calls = [f"- {n} {a}" for n, a in record["calls"]] or ["- none"]
        lines += ["Tool calls in the reply:", "", *calls, ""]
        lines += ["Answer text:", "", "```", clip(record["text"]), "```", ""]
    else:
        files = task.all_files() if task else {}
        lines += ["What the user typed:", "", *[f"- {line}" for line in result["user_lines"]], ""]
        shown = [f"- {name}: {clip(text).replace(chr(10), ' / ') or '(empty)'}" for name, text in files.items()]
        lines += ["Files in the folder (a line break shows as /):", "", *shown, ""]
        notes = [f"- {n}" for n in (task.notes if task else ())] or ["- none"]
        lines += ["Notes before the trial:", "", *notes, ""]
        lines += ["Tool actions that Korvin showed:", ""]
        lines += [f"- {a['tool']} {a['shown'] or ''} -> {a['outcome']}" for a in record["actions"]] or ["- none"]
        lines += ["", "Final answer:", "", "```", clip(record["answers"][-1] if record["answers"] else ""), "```", ""]
        lines += ["Notes file at the end:", "", "```", clip(record["notes_file"]) or "(empty)", "```", ""]
    return lines + ["Your mark (P or F): ", "", "---", ""]


def label_sample(path: Path, count: int) -> int:
    """Write a labelling sheet next to the results file. The program's verdicts are at the bottom."""
    meta, results = load(path)
    chosen = sample(results, count)
    lines = ["# Labelling sheet", "", f"Results: {Path(path).name}. Items: {len(chosen)}.", "",
             "Read each item, and decide if the model did the task well. Write P or F after \"Your mark\".",
             "Do not read the program's verdicts at the bottom before you finish.", "", "---", ""]
    for index, result in enumerate(chosen, 1):
        lines += item_lines(index, result)
    lines += ["", "", "## Program verdicts (read these only after you mark every item)", ""]
    lines += [f"- Item {i}: {'pass' if r['passed'] else 'FAIL'} ({r['task']} trial {r['trial']}, {r['reason']})"
              for i, r in enumerate(chosen, 1)]
    out = Path(path).parent / f"labels-{meta['stamp']}.md"
    out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"Wrote {len(chosen)} items to {out}")
    return 0


def agreement(path: Path) -> int:
    """Read a marked labelling sheet, and report how often the person and the program agree."""
    text = Path(path).read_text("utf-8")
    body, _sep, bottom = text.partition("## Program verdicts")
    sections = re.split(r"^## Item (\d+)", body, flags=re.MULTILINE)[1:]
    marks = {}
    for number, section in zip(sections[::2], sections[1::2]):
        found = MARK.search(section)
        marks[int(number)] = found.group(1).upper() if found and found.group(1) else None
    verdicts = {int(n): ("P" if v == "pass" else "F") for n, v in VERDICT.findall(bottom)}
    pairs = [(marks[n], verdicts[n]) for n in sorted(verdicts) if marks.get(n)]
    unmarked = [n for n in sorted(verdicts) if not marks.get(n)]
    if not pairs:
        print("No item has a mark yet. Write P or F after \"Your mark (P or F):\".")
        return 2
    agree = sum(a == b for a, b in pairs)
    print(f"Agreement: {agree} of {len(pairs)} marked items ({rate(agree, len(pairs))}). Cohen's kappa: {kappa(pairs)}.")
    if unmarked:
        print(f"Not marked: {len(unmarked)} items ({', '.join(map(str, unmarked))}).")
    details = {int(n): rest for n, rest in re.findall(r"^- Item (\d+): (.*)$", bottom, re.MULTILINE)}
    for n in sorted(verdicts):
        if marks.get(n) and marks[n] != verdicts[n]:
            print(f"  Item {n}: person {marks[n]}, program {details.get(n, verdicts[n])}")
    return 0


def kappa(pairs: list[tuple[str, str]]) -> str:
    """Return Cohen's kappa: the agreement beyond what chance would give. 1 is perfect, 0 is chance."""
    total = len(pairs)
    observed = sum(a == b for a, b in pairs) / total
    chance = sum((sum(a == m for a, _ in pairs) / total) * (sum(b == m for _, b in pairs) / total) for m in "PF")
    return "-" if chance == 1 else f"{(observed - chance) / (1 - chance):.2f}"
