import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.agent import JsonlFileSink, ModelPricing
from app.llm import OpenAIClient, ResilientClient, RetryPolicy

from .compare import compare, load_report
from .runner import RunRecord, build_report, run_suite
from .spec import load_tasks

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = (
    "You are a software engineering agent. "
    "You must ONLY call the tools explicitly provided: list_files, read_file, search_text. "
    "Never use any namespace prefixes or tools not defined. "
    "Only use workspace-relative paths. "
    "Do not invent file contents. If something does not exist, say so."
)


def _pricing() -> ModelPricing | None:
    raw_in = os.getenv("MODEL_INPUT_USD_PER_MTOK")
    raw_out = os.getenv("MODEL_OUTPUT_USD_PER_MTOK")
    if not raw_in or not raw_out:
        return None
    return ModelPricing(float(raw_in), float(raw_out))


def _client() -> ResilientClient:
    inner = OpenAIClient(system_prompt=SYSTEM_PROMPT, timeout_seconds=30.0)
    return ResilientClient(
        inner,
        RetryPolicy(max_attempts=5, base_delay_seconds=3.0, max_delay_seconds=25.0),
    )


def _print_record(record: RunRecord) -> None:
    flag = "PASS" if record.passed else "FAIL"
    detail = "" if record.passed else f" failed={record.failed_checks}"
    print(
        f"[{flag}] {record.task_id} #{record.repeat} "
        f"status={record.status} tokens={record.total_tokens} "
        f"wall={record.wall_s}s{detail}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.run")
    parser.add_argument("--version", default="dev")
    parser.add_argument("--agent-label", default="", help="label for agent/prompt version")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--task", action="append", help="limit to task id (repeatable)")
    parser.add_argument("--cooldown", type=float, default=20.0)
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="compare two report files and exit",
    )
    args = parser.parse_args(argv)

    if args.compare:
        print(
            compare(
                load_report(Path(args.compare[0])),
                load_report(Path(args.compare[1])),
            )
        )
        return 0

    load_dotenv()
    spec = load_tasks(ROOT / "evals" / "tasks.yaml")
    records = run_suite(
        spec,
        ROOT,
        _client,
        repeats=args.repeats,
        only=args.task,
        cooldown_base=args.cooldown,
        pricing=_pricing(),
        trace=JsonlFileSink(ROOT / "traces" / "eval_runs.jsonl"),
        on_record=_print_record,
    )
    report = build_report(args.version, spec, records, agent_label=args.agent_label)

    out = ROOT / "evals" / "reports" / f"{args.version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"\nversion: {report['version']} (eval_version={report['eval_version']}) "
        f"overall pass rate: {report['overall_pass_rate']:.0%} "
        f"({report['runs']} runs)"
    )
    for category, rate in report["by_category"].items():
        print(f"  {category}: {rate:.0%}")
    print(f"tokens={report['total_tokens']} cost_usd={report['total_cost_usd']}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
