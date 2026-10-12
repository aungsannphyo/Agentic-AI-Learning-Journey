import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.agent import PLANNER_V1, PROMPTS, JsonlFileSink, ModelPricing, get_prompt
from app.llm import OpenAIClient, ResilientClient, RetryPolicy

from .compare import compare, load_report
from .runner import RunRecord, build_report, run_suite
from .spec import load_tasks

ROOT = Path(__file__).resolve().parents[1]


def _pricing() -> ModelPricing | None:
    raw_in = os.getenv("MODEL_INPUT_USD_PER_MTOK")
    raw_out = os.getenv("MODEL_OUTPUT_USD_PER_MTOK")
    if not raw_in or not raw_out:
        return None
    return ModelPricing(float(raw_in), float(raw_out))


def _client(system_prompt: str) -> ResilientClient:
    inner = OpenAIClient(system_prompt=system_prompt, timeout_seconds=30.0)
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
    parser.add_argument("--prompt", default="baseline", choices=sorted(PROMPTS))
    parser.add_argument(
        "--plan",
        action="store_true",
        help="enable upfront planner (planner-v1)",
    )
    parser.add_argument("--ledger-every", type=int, default=None,
                        help="inject evidence ledger every N iterations")
    parser.add_argument("--failure-nudge", type=int, default=None)
    parser.add_argument("--retry-empty", action="store_true")
    parser.add_argument("--no-progress", type=int, default=None)
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
    prompt = get_prompt(args.prompt)
    label_parts = [prompt.label]
    if args.plan:
        label_parts.append(PLANNER_V1.label)
    if args.ledger_every:
        label_parts.append(f"ledger{args.ledger_every}")
    if args.failure_nudge:
        label_parts.append(f"fnudge{args.failure_nudge}")
    if args.retry_empty:
        label_parts.append("retryempty")
    if args.no_progress:
        label_parts.append(f"noprog{args.no_progress}")
    agent_label = args.agent_label or "+".join(label_parts)
    records = run_suite(
        spec,
        ROOT,
        lambda: _client(prompt.text),
        repeats=args.repeats,
        only=args.task,
        cooldown_base=args.cooldown,
        pricing=_pricing(),
        trace=JsonlFileSink(ROOT / "traces" / f"eval_{args.version}.jsonl"),
        on_record=_print_record,
        use_plan=args.plan,
        ledger_every=args.ledger_every,
        failure_nudge_after=args.failure_nudge,
        retry_empty_answer=args.retry_empty,
        no_progress_after=args.no_progress,
    )
    report = build_report(args.version, spec, records, agent_label=agent_label)

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
