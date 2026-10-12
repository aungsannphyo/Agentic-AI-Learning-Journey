import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest

from evals.graders import RunResult, contains_word, grade
from evals.spec import Expect, Task, load_tasks

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "shop"
TASKS = {t.id: t for t in load_tasks(ROOT / "evals" / "tasks.yaml").tasks}


def run(
    answer: str,
    *,
    read: Iterable[str] = (),
    status: str = "completed",
    workspace: Path | None = None,
) -> RunResult:
    return RunResult(
        status=status,
        answer=answer,
        read_paths=frozenset(read),
        fixture_dir=FIXTURE,
        workspace_dir=workspace,
    )


def test_word_boundary_rejects_embedded_numbers() -> None:
    assert contains_word("the limit is 20", "20")
    assert contains_word("limit: 20.", "20")
    assert not contains_word("since 2020", "20")
    assert not contains_word("limit 20.5", "20")
    assert not contains_word("rate 0.07", "07")


def test_word_boundary_accepts_trailing_zero_decimals() -> None:
    assert contains_word("free from $50.00 or more", "50")
    assert contains_word("limit is 20.", "20")
    assert not contains_word("limit 20.5", "20")
    assert not contains_word("since 2020", "20")


def test_word_boundary_matches_paths_case_insensitively() -> None:
    assert contains_word("See `SRC/Pricing.py`.", "src/pricing.py")


def test_correct_answer_with_read_passes_fully() -> None:
    g = grade(TASKS["read-max-items"], run("The maximum is 20 items.", read=["src/config.py"]))
    assert g.passed and g.score == 1.0


def test_correct_answer_without_reading_is_partial() -> None:
    g = grade(TASKS["read-max-items"], run("The maximum is 20 items."))
    assert not g.passed
    assert g.score == pytest.approx(2 / 3)
    assert [c.name for c in g.checks if not c.passed] == ["must_read"]


def test_wrong_answer_fails_answer_check_only() -> None:
    g = grade(TASKS["read-max-items"], run("It is 2020.", read=["src/config.py"]))
    assert [c.name for c in g.checks if not c.passed] == ["answer"]


def test_decoy_mention_fails_forbidden_check() -> None:
    task = TASKS["find-discount-file"]
    ok = grade(task, run("It is src/pricing.py."))
    bad = grade(task, run("src/pricing.py, also src/legacy_pricing.py."))
    assert ok.passed
    assert not bad.passed
    assert any(c.name == "forbidden:legacy_pricing" and not c.passed for c in bad.checks)


def test_decoy_only_answer_fails() -> None:
    g = grade(TASKS["find-discount-file"], run("src/legacy_pricing.py"))
    assert not g.passed


def test_contains_any_accepts_either_form() -> None:
    task = TASKS["read-tax-rate"]
    assert grade(task, run("7% tax", read=["src/config.py"])).passed
    assert grade(task, run("TAX_RATE is 0.07", read=["src/config.py"])).passed


def test_incomplete_run_fails_everything() -> None:
    g = grade(TASKS["read-max-items"], run("20", read=["src/config.py"], status="timeout"))
    assert not g.passed
    assert g.score < 0.5
    assert g.checks[0].detail == "status=timeout"


def test_refusal_passes_on_honest_answer() -> None:
    g = grade(TASKS["negative-payment"], run("There is no payment processing in this repo."))
    assert g.passed


def test_refusal_fails_on_invented_file() -> None:
    g = grade(
        TASKS["negative-payment"],
        run("Payments are not tested, but see src/payments.py."),
    )
    assert not g.passed
    assert any(c.name == "no_invented_path" and not c.passed for c in g.checks)


def test_refusal_may_mention_real_files() -> None:
    g = grade(
        TASKS["negative-email"],
        run("I could not find any SMTP setup; src/config.py has no email settings."),
    )
    assert g.passed


def test_refusal_may_mention_real_files_by_basename() -> None:
    g = grade(
        TASKS["negative-payment"],
        run(
            "The repository does not contain any file that handles credit‑card payment processing. "
            "None of the source files (e.g., `orders.py`, `pricing.py`, etc.) include code related "
            "to credit‑card or payment handling."
        ),
    )
    assert g.passed
    assert all(c.passed for c in g.checks)


def test_refusal_fails_on_invented_basename() -> None:
    g = grade(
        TASKS["negative-payment"],
        run("No payment code found, but see billing.py."),
    )
    assert not g.passed
    assert any(c.name == "no_invented_path" and not c.passed for c in g.checks)


def test_refusal_fails_on_confident_fabrication() -> None:
    g = grade(TASKS["negative-email"], run("It uses smtp.gmail.com on port 587."))
    assert any(c.name == "refusal_cue" and not c.passed for c in g.checks)


def test_edit_check_reads_workspace_and_unchanged(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    shutil.copytree(FIXTURE, ws)
    task = TASKS["edit-add-currency-symbol"]

    untouched = grade(task, run("done", workspace=ws))
    assert not untouched.passed

    cfg = ws / "src" / "config.py"
    cfg.write_text(cfg.read_text(encoding="utf-8") + 'CURRENCY_SYMBOL = "$"\n', encoding="utf-8")
    assert grade(task, run("done", workspace=ws)).passed

    (ws / "src" / "pricing.py").write_text("# vandalized\n", encoding="utf-8")
    broken = grade(task, run("done", workspace=ws))
    assert any(c.name == "unchanged" and not c.passed for c in broken.checks)


def test_edit_without_workspace_fails_cleanly() -> None:
    g = grade(TASKS["edit-add-currency-symbol"], run("done"))
    assert not g.passed


def test_spec_requires_values_unless_refusal() -> None:
    with pytest.raises(ValueError, match="requires values"):
        Expect(kind="answer_contains_all")
    assert Expect(kind="refusal").values == []


def test_every_enabled_task_is_gradable() -> None:
    for task in load_tasks(ROOT / "evals" / "tasks.yaml").enabled_tasks():
        g = grade(task, run("", status="llm_failed"))
        assert not g.passed
        assert 0.0 <= g.score <= 1.0


def test_task_type_is_pydantic_task() -> None:
    assert isinstance(TASKS["find-discount-file"], Task)


def test_word_boundary_matches_hyphenated_range() -> None:
    assert contains_word("percent range is 0-100", "100")
    assert contains_word("between 0 and 100", "100")
    assert contains_word("0 to 100%", "100")


def _neg(task_id: str) -> Task:
    spec = load_tasks(ROOT / "evals" / "tasks.yaml")
    return next(t for t in spec.tasks if t.id == task_id)


@pytest.mark.parametrize("answer", [
    "I could not find it, but it is probably handled by Stripe.",
    "No payment code here; see the payments module for details.",
    "Payments are not in orders.py; check billing_service instead.",
    "There is no such file, though checkout probably calls PayPal.",
])
def test_characterize_refusal_grader_on_hedged_fabrication(answer: str) -> None:
    result = RunResult("completed", answer, frozenset(), FIXTURE)
    g = grade(_neg("negative-payment"), result)
    print(answer, "->", g.passed, [c.name for c in g.checks if not c.passed])


@pytest.mark.parametrize("answer, should_pass", [
    ("No payment code here; see the payments module for details.", False),
    ("Payments are not in orders.py; check billing_service instead.", False),
    ("The repository does not contain any file that handles it.", True),
    ("None of the source files (e.g., orders.py, pricing.py) handle it.", True),
    ("I'm unable to find an SMTP server; the codebase has no mail settings.", True),
    ("I could not find it, but try the gateway helper.", False),
])
def test_refusal_grader_rejects_pointers_to_nonexistent_things(
    answer: str, should_pass: bool
) -> None:
    task_id = "negative-email" if "SMTP" in answer else "negative-payment"
    result = RunResult("completed", answer, frozenset(), FIXTURE)
    g = grade(_neg(task_id), result)
    assert g.passed == should_pass, f"failed for answer: {answer}, checks: {[c.name for c in g.checks if not c.passed]}"


@pytest.mark.parametrize("answer", [
    "Not found; see the pricing module for discounts.",
    "No payment code; check config.py for shop constants.",
    "Not implemented in orders.py; see README.md for architecture notes.",
])
def test_refusal_grader_allows_pointers_to_real_fixture_entities(answer: str) -> None:
    result = RunResult("completed", answer, frozenset(), FIXTURE)
    g = grade(_neg("negative-payment"), result)
    assert g.passed, f"unexpected failure for real entity pointer: {answer}, failed: {[c.name for c in g.checks if not c.passed]}"


@pytest.mark.parametrize("answer", [
    "No payment code here; it is likely implemented by the gateway layer.",
    "Payments are not in orders.py; consult the billing team's docs instead.",
    "Unable to find SMTP server; the system probably integrates an external mail vendor.",
])
@pytest.mark.xfail(reason="known limitation: prose/indirect fabrication without explicit pointer verbs", strict=True)
def test_heuristic_grader_known_limitations_on_indirect_fabrication(answer: str) -> None:
    task_id = "negative-email" if "SMTP" in answer else "negative-payment"
    result = RunResult("completed", answer, frozenset(), FIXTURE)
    g = grade(_neg(task_id), result)
    assert not g.passed, f"expected rejection, but passed: {answer}"
