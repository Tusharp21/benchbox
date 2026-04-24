from __future__ import annotations

from pytestqt.qtbot import QtBot

from benchbox_gui.workers import OperationWorker


def test_operation_worker_emits_succeeded_with_return_value(qtbot: QtBot) -> None:
    worker = OperationWorker(lambda: {"result": 42})

    with qtbot.waitSignal(worker.succeeded, timeout=2000) as blocker:
        worker.start()
    worker.wait()

    assert blocker.args == [{"result": 42}]


def test_operation_worker_emits_failed_on_exception(qtbot: QtBot) -> None:
    def boom() -> None:
        raise RuntimeError("nope")

    worker = OperationWorker(boom)

    with qtbot.waitSignal(worker.failed, timeout=2000) as blocker:
        worker.start()
    worker.wait()

    exc = blocker.args[0]
    assert isinstance(exc, RuntimeError)
    assert str(exc) == "nope"


def test_operation_worker_never_fires_both_signals(qtbot: QtBot) -> None:
    events: list[str] = []

    worker_ok = OperationWorker(lambda: "ok")
    worker_ok.succeeded.connect(lambda _: events.append("ok-success"))
    worker_ok.failed.connect(lambda _: events.append("ok-fail"))

    with qtbot.waitSignal(worker_ok.succeeded, timeout=2000):
        worker_ok.start()
    worker_ok.wait()

    assert events == ["ok-success"]
