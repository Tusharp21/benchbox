"""MariaDB inventory + drop helpers, used by the GUI Databases page.

Listing and dropping are done through the ``mysql`` CLI so the install
profile (mariadb-server already on the box, ``mysql`` on PATH) is the
only requirement. The root password is passed via the ``MYSQL_PWD``
environment variable instead of ``-p<pw>`` so it doesn't leak in the
process listing.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from benchbox_core import discovery, introspect
from benchbox_core.logs import get_logger

_log = get_logger(__name__)

# MariaDB-internal schemas we never want to touch or surface as orphans.
SYSTEM_DATABASES: frozenset[str] = frozenset(
    {"mysql", "information_schema", "performance_schema", "sys"}
)

DEFAULT_MYSQL_BIN: str = "mysql"


class DatabaseError(RuntimeError):
    """Raised when a mysql CLI invocation fails."""


@dataclass(frozen=True)
class DatabaseInfo:
    name: str
    size_bytes: int
    site_name: str | None = None
    bench_path: Path | None = None

    @property
    def is_orphan(self) -> bool:
        return self.site_name is None

    @property
    def is_system(self) -> bool:
        return self.name in SYSTEM_DATABASES


# A small indirection so tests can stub the CLI without monkey-patching
# subprocess directly.
MysqlRunner = Callable[[list[str], str], "subprocess.CompletedProcess[str]"]


def _default_runner(argv: list[str], password: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MYSQL_PWD"] = password
    _log.debug("mysql %s", " ".join(argv[1:]))
    return subprocess.run(  # noqa: S603 — argv list, never shell=True
        argv,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _query(
    sql: str,
    *,
    db_root_password: str,
    mysql_bin: str = DEFAULT_MYSQL_BIN,
    runner: MysqlRunner | None = None,
) -> list[list[str]]:
    """Run a query in batch/skip-headers mode and return rows of fields."""
    argv = [mysql_bin, "-u", "root", "-B", "-N", "-e", sql]
    active = runner or _default_runner
    proc = active(argv, db_root_password)
    if proc.returncode != 0:
        raise DatabaseError(
            f"mysql query failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip() or 'no output'}"
        )
    rows: list[list[str]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        rows.append(line.split("\t"))
    return rows


def _execute(
    sql: str,
    *,
    db_root_password: str,
    mysql_bin: str = DEFAULT_MYSQL_BIN,
    runner: MysqlRunner | None = None,
) -> None:
    argv = [mysql_bin, "-u", "root", "-e", sql]
    active = runner or _default_runner
    proc = active(argv, db_root_password)
    if proc.returncode != 0:
        raise DatabaseError(
            f"mysql command failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip() or 'no output'}"
        )


def _site_db_index(bench_paths: Iterable[Path]) -> dict[str, tuple[str, Path]]:
    """Map db_name -> (site_name, bench_path) for every site we can find."""
    index: dict[str, tuple[str, Path]] = {}
    for bench in bench_paths:
        try:
            info = introspect.introspect(bench)
        except OSError:
            continue
        for site in info.sites:
            if site.db_name:
                index[site.db_name] = (site.name, info.path)
    return index


def list_databases(
    *,
    db_root_password: str,
    mysql_bin: str = DEFAULT_MYSQL_BIN,
    runner: MysqlRunner | None = None,
    include_system: bool = False,
    bench_paths: Iterable[Path] | None = None,
) -> list[DatabaseInfo]:
    """Return one ``DatabaseInfo`` per database on the local server.

    Each row carries the on-disk size (``data_length + index_length``)
    and is annotated with the owning site/bench when introspect can find
    it. Databases that don't map to any known site are returned with
    ``site_name=None`` (``is_orphan`` is True).
    """
    sql = (
        "SELECT TABLE_SCHEMA, COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) "
        "FROM information_schema.TABLES "
        "GROUP BY TABLE_SCHEMA "
        "UNION "
        "SELECT SCHEMA_NAME, 0 "
        "FROM information_schema.SCHEMATA "
        "WHERE SCHEMA_NAME NOT IN ("
        "SELECT DISTINCT TABLE_SCHEMA FROM information_schema.TABLES);"
    )
    rows = _query(sql, db_root_password=db_root_password, mysql_bin=mysql_bin, runner=runner)

    paths = list(bench_paths) if bench_paths is not None else list(discovery.discover_benches())
    site_index = _site_db_index(paths)

    out: list[DatabaseInfo] = []
    for row in rows:
        if len(row) < 2:
            continue
        name = row[0]
        if not include_system and name in SYSTEM_DATABASES:
            continue
        try:
            size = int(row[1])
        except ValueError:
            size = 0
        owner = site_index.get(name)
        out.append(
            DatabaseInfo(
                name=name,
                size_bytes=size,
                site_name=owner[0] if owner else None,
                bench_path=owner[1] if owner else None,
            )
        )
    out.sort(key=lambda d: (not d.is_orphan, d.name.lower()))
    return out


def drop_database(
    name: str,
    *,
    db_root_password: str,
    mysql_bin: str = DEFAULT_MYSQL_BIN,
    runner: MysqlRunner | None = None,
) -> None:
    """Drop a database. Refuses system schemas as a safety stop."""
    if name in SYSTEM_DATABASES:
        raise DatabaseError(f"refusing to drop system database {name!r}")
    if not name or any(c in name for c in "`\\\n\t ") or "'" in name or '"' in name:
        raise DatabaseError(f"refusing to drop database with unsafe name {name!r}")
    _execute(
        f"DROP DATABASE `{name}`;",
        db_root_password=db_root_password,
        mysql_bin=mysql_bin,
        runner=runner,
    )


@dataclass(frozen=True)
class DatabaseSummary:
    total: int
    allocated: int
    orphan: int
    total_bytes: int = field(default=0)


def summarize(databases: Iterable[DatabaseInfo]) -> DatabaseSummary:
    total = 0
    allocated = 0
    orphan = 0
    total_bytes = 0
    for db in databases:
        total += 1
        total_bytes += db.size_bytes
        if db.is_orphan:
            orphan += 1
        else:
            allocated += 1
    return DatabaseSummary(
        total=total, allocated=allocated, orphan=orphan, total_bytes=total_bytes
    )
