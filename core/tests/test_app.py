from __future__ import annotations

from pathlib import Path

import pytest

from benchbox_core.app import (
    AppOperationError,
    get_app,
    install_app,
    remove_app,
    uninstall_app,
)
from benchbox_core.installer._run import CommandResult, CommandRunner


class CapturingRunner(CommandRunner):
    """Records every run() call (argv + cwd) and returns a canned rc."""

    def __init__(self, *, returncode: int = 0, post_run: object | None = None) -> None:
        super().__init__(dry_run=False)
        self._returncode = returncode
        self._post_run = post_run
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: str | Path | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        argv = tuple(command)
        self.calls.append((argv, str(cwd) if cwd is not None else None))
        if callable(self._post_run):
            self._post_run()
        stderr = "" if self._returncode == 0 else "boom"
        return CommandResult(argv, self._returncode, "", stderr, True)


def _make_bench_skeleton(path: Path) -> None:
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text("{}", encoding="utf-8")


def _add_app_dir(bench_path: Path, app_name: str, version: str = "1.0.0") -> None:
    app_dir = bench_path / "apps" / app_name / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    sites_apps = bench_path / "sites" / "apps.txt"
    content = sites_apps.read_text().splitlines()
    if app_name not in content:
        sites_apps.write_text("\n".join([*content, app_name]) + "\n", encoding="utf-8")


# --- get_app ------------------------------------------------------


def test_get_app_argv_shape_and_cwd(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _add_app_dir(bench, "erpnext", "15.0.0"),
    )

    get_app(bench, "https://github.com/frappe/erpnext", runner=runner)

    argv, cwd = runner.calls[0]
    assert argv == ("bench", "get-app", "https://github.com/frappe/erpnext")
    assert cwd == str(bench)


def test_get_app_flags_forward(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _add_app_dir(bench, "hrms"),
    )

    get_app(
        bench,
        "https://github.com/frappe/hrms",
        branch="develop",
        overwrite=True,
        skip_assets=True,
        resolve_deps=True,
        runner=runner,
    )

    argv = runner.calls[0][0]
    assert "--branch" in argv
    assert argv[argv.index("--branch") + 1] == "develop"
    assert "--overwrite" in argv
    assert "--skip-assets" in argv
    assert "--resolve-deps" in argv


def test_get_app_returns_populated_apps_list(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _add_app_dir(bench, "erpnext", "15.1.0"),
    )

    result = get_app(bench, "https://github.com/frappe/erpnext", runner=runner)

    app_names = {a.name for a in result.apps}
    assert "frappe" in app_names
    assert "erpnext" in app_names
    erpnext = next(a for a in result.apps if a.name == "erpnext")
    assert erpnext.version == "15.1.0"


def test_get_app_raises_on_nonzero_exit(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=1)

    with pytest.raises(AppOperationError) as excinfo:
        get_app(bench, "https://github.com/frappe/erpnext", runner=runner)

    assert excinfo.value.operation == "get-app"
    assert excinfo.value.result.returncode == 1


def test_get_app_dry_run_returns_empty_apps(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    dry = CommandRunner(dry_run=True)

    result = get_app(bench, "https://github.com/frappe/erpnext", runner=dry)

    assert result.command.executed is False
    assert result.apps == ()


# --- install_app --------------------------------------------------


def test_install_app_uses_global_site_flag_before_subcommand(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    install_app(bench, "site1.local", ["erpnext"], runner=runner)

    argv, cwd = runner.calls[0]
    # bench --site <name> install-app <app>, not bench install-app --site ...
    assert argv[:4] == ("bench", "--site", "site1.local", "install-app")
    assert argv[4] == "erpnext"
    assert cwd == str(bench)


def test_install_app_multiple_apps_in_one_call(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    install_app(bench, "site1.local", ["erpnext", "hrms", "crm"], runner=runner)

    argv = runner.calls[0][0]
    # Apps come after install-app, in the order given.
    assert argv[4:] == ("erpnext", "hrms", "crm")


def test_install_app_force_flag_appended_at_end(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    install_app(bench, "s.local", ["erpnext"], force=True, runner=runner)

    argv = runner.calls[0][0]
    assert "--force" in argv


def test_install_app_empty_apps_list_raises(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    with pytest.raises(ValueError, match="at least one app"):
        install_app(bench, "s.local", [], runner=runner)
    assert runner.calls == []  # must not spawn anything


def test_install_app_raises_on_nonzero_exit(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=1)

    with pytest.raises(AppOperationError) as excinfo:
        install_app(bench, "s.local", ["erpnext"], runner=runner)
    assert excinfo.value.operation == "install-app"


# --- uninstall_app ------------------------------------------------


def test_uninstall_app_yes_is_on_by_default(tmp_path: Path) -> None:
    # Default --yes so a non-TTY subprocess doesn't hang on confirmation.
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    uninstall_app(bench, "s.local", "erpnext", runner=runner)

    argv, cwd = runner.calls[0]
    assert argv[:4] == ("bench", "--site", "s.local", "uninstall-app")
    assert argv[4] == "erpnext"
    assert "--yes" in argv
    assert cwd == str(bench)


def test_uninstall_app_yes_can_be_disabled(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    uninstall_app(bench, "s.local", "erpnext", yes=False, runner=runner)

    assert "--yes" not in runner.calls[0][0]


def test_uninstall_app_no_backup_and_force_flags(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    uninstall_app(bench, "s.local", "erpnext", no_backup=True, force=True, runner=runner)

    argv = runner.calls[0][0]
    assert "--no-backup" in argv
    assert "--force" in argv


def test_uninstall_app_raises_on_nonzero_exit(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=1)

    with pytest.raises(AppOperationError) as excinfo:
        uninstall_app(bench, "s.local", "erpnext", runner=runner)

    assert excinfo.value.operation == "uninstall-app"


# --- remove_app ---------------------------------------------------


def test_remove_app_argv_shape_and_cwd(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    remove_app(bench, "erpnext", runner=runner)

    argv, cwd = runner.calls[0]
    assert argv[:3] == ("bench", "remove-app", "erpnext")
    assert "--no-backup" not in argv
    assert "--force" not in argv
    assert cwd == str(bench)


def test_remove_app_flag_forwarding(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=0)

    remove_app(bench, "erpnext", no_backup=True, force=True, runner=runner)

    argv = runner.calls[0][0]
    assert "--no-backup" in argv
    assert "--force" in argv


def test_remove_app_raises_on_failure(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=1)

    with pytest.raises(AppOperationError) as excinfo:
        remove_app(bench, "erpnext", runner=runner)

    assert excinfo.value.operation == "remove-app"


def test_site_config_is_not_required_for_app_ops(tmp_path: Path) -> None:
    # App operations only need the bench dir to exist; no site-config
    # prerequisites from our side (bench itself will complain if missing).
    bench = tmp_path / "bare-bench"
    (bench / "apps" / "frappe").mkdir(parents=True, exist_ok=True)
    runner = CapturingRunner(returncode=0)

    install_app(bench, "s.local", ["erpnext"], runner=runner)
    assert runner.calls
