import json
from pathlib import Path
from typing import Any

THRESHOLD = 0.2  # pass-rate change that counts as a real movement at small N


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(old: dict[str, Any], new: dict[str, Any]) -> str:
    warning: list[str] = []
    old_ev, new_ev = old.get("eval_version", 1), new.get("eval_version", 1)
    if old_ev != new_ev:
        warning = [
            (
                f"WARNING: eval_version {old_ev} -> {new_ev}: grader/tasks changed, "
                "differences are NOT purely agent changes"
            ),
            "",
        ]
    old_tasks = {t["task_id"]: t for t in old["tasks"]}
    new_tasks = {t["task_id"]: t for t in new["tasks"]}
    lines = [
        *warning,
        f"{old['version']} -> {new['version']}",
        (
            f"overall pass rate: {old['overall_pass_rate']:.0%} -> "
            f"{new['overall_pass_rate']:.0%}"
        ),
        f"tokens: {old['total_tokens']} -> {new['total_tokens']}",
        "",
    ]
    for task_id in sorted(set(old_tasks) | set(new_tasks)):
        a, b = old_tasks.get(task_id), new_tasks.get(task_id)
        if a is None or b is None:
            side = "only in new" if a is None else "only in old"
            lines.append(f"  {task_id}: {side}")
            continue
        delta = b["pass_rate"] - a["pass_rate"]
        mark = (
            "REGRESSION" if delta <= -THRESHOLD
            else "IMPROVED" if delta >= THRESHOLD
            else "same"
        )
        lines.append(
            f"  {task_id}: {a['pass_rate']:.0%} -> {b['pass_rate']:.0%}  {mark}"
        )
    lines.append("")
    lines.append(
        f"note: differences under {THRESHOLD:.0%} are within noise at small N"
    )
    return "\n".join(lines)
