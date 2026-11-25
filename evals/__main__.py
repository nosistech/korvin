"""Run Korvin's evals from the command line with: python -m evals

The evals give real tasks to the real model through Korvin, and a program decides each pass or fail.
The same command also grades a saved run again, compares two runs, and makes a labelling sheet.
"""

import argparse
import fnmatch
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from evals import ollama_info, review, runner
from evals.decision import run_case
from evals.grading import entry
from evals.metrics import family_name
from evals.report import write_results
from evals.runner import run_trial
from evals.runrecord import static_meta, task_fingerprint
from evals.tasks import ALL
from evals.tasks.tool_servers import clock_settings
from korvin import guard

DEFAULT_OUT = Path(__file__).resolve().parent / "results"
LONG_KINDS = ("context", "overflow")


def main(argv: list[str] | None = None) -> int:
    """Run the chosen tasks and write the results, or do one of the offline jobs. Return the exit code."""
    guard.install()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    if args.rescore:
        return review.rescore(Path(args.rescore))
    if args.compare:
        return review.compare(Path(args.compare[0]), Path(args.compare[1]))
    if args.label_sample:
        return review.label_sample(Path(args.label_sample), args.n)
    if args.agreement:
        return review.agreement(Path(args.agreement))
    chosen = select(args.tasks, args.skip)
    if args.list:
        print_list(chosen)
        return 0
    if not chosen:
        print("No task matches the given patterns. Use --list to see the tasks.", file=sys.stderr)
        return 2
    return run(args, chosen, ["python", "-m", "evals", *argv])


def run(args: argparse.Namespace, chosen: list, command: list[str]) -> int:
    """Check Ollama, run every trial, and write the results."""
    meta = {**static_meta(command), "task_fingerprint": task_fingerprint(chosen)}  # taken before the first trial
    try:
        info = ollama_info.check_ready(args.model)
        meta.update(ollama_version=ollama_info.version(),
                    model_parameters=" ".join(ollama_info.show(args.model)["parameters"].split()))
    except ollama_info.NotReady as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Context {info.context_length:,} tokens. {round(100 * info.gpu_share)}% of the model on the graphics card.")
    if args.with_clock:
        runner.EXTRA_SERVERS.update(clock_settings())
        meta["with_clock"] = True
    started, start, results, stopped = datetime.now(), time.monotonic(), [], False
    stamp = started.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    partial = out / f"results-{stamp}.partial.jsonl"  # kept only while the run lasts, in case it breaks off
    plan = [(n, item) for n in range(1, max(trials(i, args) for i in chosen) + 1) for item in chosen
            if n <= trials(item, args)]
    try:
        for index, (number, item) in enumerate(plan, 1):
            result = run_one(item, number, args)
            results.append(result)
            with open(partial, "a", encoding="utf-8") as file:
                file.write(json.dumps(result, ensure_ascii=False) + "\n")
            mark = "pass" if result["passed"] else "FAIL - " + result["reason"]
            print(f"[{index}/{len(plan)}] {item.id} trial {number}: {mark} ({result['seconds']:.0f} s)", flush=True)
    except KeyboardInterrupt:
        stopped = True
        print("Stopped. Writing the results of the finished trials.")
    after = ollama_info.loaded_model(args.model)
    meta.update({
        "stamp": stamp, "date": started.strftime("%Y-%m-%d %H:%M"), "start": started.isoformat(timespec="seconds"),
        "end": datetime.now().isoformat(timespec="seconds"), "model": args.model, "digest": info.digest,
        "context_length": info.context_length,
        "context_after": after.context_length if after else None, "min_context": ollama_info.MIN_CONTEXT,
        "size": info.size, "size_vram": info.size_vram, "gpu_share": round(info.gpu_share, 4),
        "loaded_after": ollama_info.loaded_names(), "trials": args.trials, "decision_trials": args.decision_trials,
        "context_trials": args.context_trials, "timeout": args.timeout, "context_timeout": args.context_timeout,
        "total_seconds": round(time.monotonic() - start, 1), "stopped_early": stopped,
        "tasks": [item.id for item in chosen],
    })
    json_path, report_path = write_results(out, meta, results)
    partial.unlink(missing_ok=True)
    passed = sum(r["passed"] for r in results)
    print(f"{passed} of {len(results)} trials passed.\nResults: {json_path}\nReport:  {report_path}")
    return 0


def trials(item, args: argparse.Namespace) -> int:
    """Return the number of trials for a task or a case."""
    if item.target == "decision":
        return args.decision_trials
    return args.context_trials if item.kind in LONG_KINDS else args.trials


def run_one(item, number: int, args: argparse.Namespace) -> dict:
    """Run one trial of a task or a case, grade it, and return its result entry."""
    if item.target == "decision":
        return entry(item, number, run_case(item, number, args.model))
    timeout = args.context_timeout if item.kind in LONG_KINDS else args.timeout
    return entry(item, number, run_trial(item, number, args.model, timeout))


def select(patterns: list[str] | None, skip: list[str] | None) -> list:
    """Return the tasks and cases whose id or kind matches a pattern, such as "chain-*" or "context"."""
    def matches(item, chosen: list[str]) -> bool:
        return any(fnmatch.fnmatch(item.id, p) or fnmatch.fnmatch(item.kind, p) for p in chosen)

    items = [item for item in ALL if not patterns or matches(item, patterns)]
    return [item for item in items if not skip or not matches(item, skip)]


def print_list(chosen: list) -> None:
    """Print the tasks and cases, grouped by family, with counts."""
    families: dict[int, list] = {}
    for item in chosen:
        families.setdefault(item.family_number, []).append(item)
    for family in sorted(families):
        items = families[family]
        print(f"\n{family_name(family)}: {len(items)}")
        for item in items:
            print(f"  {item.id:42} {item.kind:20} steps {item.steps:<3} {item.user_lines[-1][:60]}")
    tasks = sum(item.target == "task" for item in chosen)
    print(f"\nTotal: {tasks} whole tasks and {len(chosen) - tasks} decision cases.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(prog="evals", description="Run Korvin's evals against a local model.")
    parser.add_argument("--model", default="qwen", help="the Ollama model name (default: qwen)")
    parser.add_argument("--trials", type=int, default=5, help="trials for each whole task (default: 5)")
    parser.add_argument("--decision-trials", type=int, default=20, help="trials for each decision case (default: 20)")
    parser.add_argument("--context-trials", type=int, default=3, help="trials for each long-context task (default: 3)")
    parser.add_argument("--tasks", nargs="+", metavar="PATTERN", help="run only tasks whose id or kind matches")
    parser.add_argument("--skip", nargs="+", metavar="PATTERN", help="leave out tasks whose id or kind matches")
    parser.add_argument("--list", action="store_true", help="list the tasks and stop")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="the folder for the results (default: evals/results)")
    parser.add_argument("--timeout", type=float, default=300, help="the longest time for one trial, in seconds")
    parser.add_argument("--context-timeout", type=float, default=900,
                        help="the longest time for one long-context trial, in seconds (default: 900)")
    parser.add_argument("--with-clock", action="store_true",
                        help="give every task the example clock server too, to measure what server tools cost")
    parser.add_argument("--rescore", metavar="RESULTS", help="grade a saved results file again, with no model")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two saved results files")
    parser.add_argument("--label-sample", metavar="RESULTS", help="write a labelling sheet for a person")
    parser.add_argument("--n", type=int, default=40, help="the number of items on the labelling sheet (default: 40)")
    parser.add_argument("--agreement", metavar="SHEET", help="count the agreement on a marked labelling sheet")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
