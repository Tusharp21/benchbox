from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from benchbox_core import database
from benchbox_core.database import (
    DatabaseError,
    DatabaseInfo,
    drop_database,
    list_databases,
    summarize,
)


def _bench_with_site(root: Path, name: str, site: str, db_name: str) -> Path:
    bench = root / name
    (bench / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (bench / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    sites = bench / "sites"
    sites.mkdir(parents=True, exist_ok=True)
    (sites / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (sites / "common_site_config.json").write_text("{}", encoding="utf-8")
    site_dir = sites / site
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "site_config.json").write_text(
        json.dumps({"db_name": db_name}), encoding="utf-8"
    )
    (site_dir / "apps.txt").write_text("frappe\n", encoding="utf-8")
    return bench.resolve()


def _fake_runner(stdout: str = "", stderr: str = "", returncode: int = 0):
    calls: list[tuple[list[str], str]] = []

    def runner(argv: list[str], password: str) -> subprocess.CompletedProcess[str]:
        calls.append((argv, password))
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_list_databases_marks_allocated_and_orphan(tmp_path: Path) -> None:
    bench = _bench_with_site(tmp_path, "bench-a", "shop.local", "_shop")
    stdout = (
        "_shop\t12345\n"
        "_lost\t9999\n"
        "mysql\t100\n"
        "performance_schema\t0\n"
    )
    runner = _fake_runner(stdout=stdout)

    rows = list_databases(
        db_root_password="root",
        runner=runner,
        bench_paths=[bench],
    )

    by_name = {r.name: r for r in rows}
    assert "mysql" not in by_name
    assert "performance_schema" not in by_name
    assert by_name["_shop"].is_orphan is False
    assert by_name["_shop"].site_name == "shop.local"
    assert by_name["_shop"].bench_path == bench
    assert by_name["_shop"].size_bytes == 12345
    assert by_name["_lost"].is_orphan is True
    assert by_name["_lost"].site_name is None


def test_list_databases_password_passed_through_runner(tmp_path: Path) -> None:
    runner = _fake_runner(stdout="_orph\t0\n")
    list_databases(db_root_password="hunter2", runner=runner, bench_paths=[])
    assert runner.calls[0][1] == "hunter2"  # type: ignore[attr-defined]
    assert runner.calls[0][0][0] == "mysql"  # type: ignore[attr-defined]


def test_list_databases_includes_system_when_requested(tmp_path: Path) -> None:
    runner = _fake_runner(stdout="mysql\t10\n_x\t0\n")
    rows = list_databases(
        db_root_password="root",
        runner=runner,
        bench_paths=[],
        include_system=True,
    )
    names = {r.name for r in rows}
    assert names == {"mysql", "_x"}


def test_list_databases_raises_on_failure() -> None:
    runner = _fake_runner(stderr="ERROR 1045 (28000): Access denied", returncode=1)
    with pytest.raises(DatabaseError, match="Access denied"):
        list_databases(db_root_password="root", runner=runner, bench_paths=[])


def test_drop_database_runs_drop_query() -> None:
    runner = _fake_runner()
    drop_database("_orphan", db_root_password="root", runner=runner)
    argv, _ = runner.calls[0]  # type: ignore[attr-defined]
    assert argv[:4] == ["mysql", "-u", "root", "-e"]
    assert "DROP DATABASE `_orphan`" in argv[4]


def test_drop_database_refuses_system_database() -> None:
    runner = _fake_runner()
    with pytest.raises(DatabaseError, match="system database"):
        drop_database("mysql", db_root_password="root", runner=runner)
    assert runner.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("bad", ["x`y", "x\ny", "a b", "a'b", 'a"b', ""])
def test_drop_database_refuses_unsafe_names(bad: str) -> None:
    runner = _fake_runner()
    with pytest.raises(DatabaseError):
        drop_database(bad, db_root_password="root", runner=runner)
    assert runner.calls == []  # type: ignore[attr-defined]


def test_drop_database_propagates_mysql_failure() -> None:
    runner = _fake_runner(stderr="ERROR 1008", returncode=1)
    with pytest.raises(DatabaseError, match="ERROR 1008"):
        drop_database("_orphan", db_root_password="root", runner=runner)


def test_summarize_counts_orphan_and_allocated() -> None:
    items = [
        DatabaseInfo(name="_a", size_bytes=10, site_name="a.local", bench_path=Path("/b")),
        DatabaseInfo(name="_b", size_bytes=5, site_name=None, bench_path=None),
        DatabaseInfo(name="_c", size_bytes=20, site_name=None, bench_path=None),
    ]
    s = summarize(items)
    assert s.total == 3
    assert s.allocated == 1
    assert s.orphan == 2
    assert s.total_bytes == 35


def test_default_runner_uses_mysql_pwd_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv, env, capture_output, text, check):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        captured["mysql_pwd"] = env.get("MYSQL_PWD")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    database._default_runner(["mysql", "-V"], "secret")  # noqa: SLF001
    assert captured["mysql_pwd"] == "secret"
    assert captured["argv"] == ["mysql", "-V"]
