from __future__ import annotations

from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    InstallResult,
    Step,
    StepResult,
)


def test_step_result_ok_true_on_success() -> None:
    step = Step("run thing", ("true",))
    result = StepResult(step=step, executed=True, skipped=False, returncode=0, error=None)
    assert result.ok is True


def test_step_result_ok_false_on_nonzero() -> None:
    step = Step("run thing", ("false",))
    result = StepResult(step=step, executed=True, skipped=False, returncode=1, error=None)
    assert result.ok is False


def test_step_result_ok_true_when_skipped() -> None:
    step = Step("already done", ("noop",), skip_reason="present")
    result = StepResult(step=step, executed=False, skipped=True, returncode=None, error=None)
    assert result.ok is True


def test_component_plan_filters_runnable_steps() -> None:
    skipped = Step("skipme", (), skip_reason="nothing to do")
    runnable = Step("do it", ("echo", "hi"))
    plan = ComponentPlan(component="test", steps=(skipped, runnable))
    assert plan.runnable_steps == (runnable,)


def test_component_result_aggregates_ok() -> None:
    step = Step("x", ("true",))
    good = StepResult(step=step, executed=True, skipped=False, returncode=0, error=None)
    bad = StepResult(step=step, executed=True, skipped=False, returncode=2, error="boom")

    assert ComponentResult(component="c", results=(good, good)).ok is True
    mixed = ComponentResult(component="c", results=(good, bad))
    assert mixed.ok is False
    assert mixed.failed == (bad,)


def test_install_result_failed_component_points_to_first_failure() -> None:
    step = Step("x", ("true",))
    ok_step = StepResult(step=step, executed=True, skipped=False, returncode=0, error=None)
    bad_step = StepResult(step=step, executed=True, skipped=False, returncode=1, error=None)

    good = ComponentResult(component="a", results=(ok_step,))
    bad = ComponentResult(component="b", results=(bad_step,))

    result = InstallResult(components=(good, bad))
    assert result.ok is False
    assert result.failed_component is bad


def test_install_result_empty_is_ok() -> None:
    assert InstallResult().ok is True
    assert InstallResult().failed_component is None
