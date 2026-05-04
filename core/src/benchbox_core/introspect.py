"""Read bench metadata from disk."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

_SITES_SKIP: frozenset[str] = frozenset({"assets", "__pycache__"})

# Frappe's default webserver port when ``webserver_port`` isn't set in
# sites/common_site_config.json. Matches the value hard-coded in Frappe's
# Procfile (``bench/config/procfile.py``).
DEFAULT_WEBSERVER_PORT: int = 8000


@dataclass(frozen=True)
class AppInfo:
    name: str
    version: str | None
    git_branch: str | None


@dataclass(frozen=True)
class SiteInfo:
    name: str
    path: Path
    db_name: str | None
    installed_apps: list[str]
    scheduler_paused: bool = False
    maintenance_mode: bool = False


@dataclass(frozen=True)
class BenchInfo:
    path: Path
    frappe_version: str | None
    python_version: str | None
    git_branch: str | None
    apps: list[AppInfo]
    sites: list[SiteInfo]
    webserver_port: int = DEFAULT_WEBSERVER_PORT


def read_app_version(app_dir: Path) -> str | None:
    # AST parse so we don't have to import the app (which needs its deps).
    init_file = app_dir / app_dir.name / "__init__.py"
    if not init_file.is_file():
        return None
    try:
        tree = ast.parse(init_file.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "__version__"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
    return None


def read_git_branch(repo_dir: Path) -> str | None:
    head = repo_dir / ".git" / "HEAD"
    if not head.is_file():
        return None
    try:
        content = head.read_text().strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    if content.startswith(prefix):
        return content[len(prefix) :]
    return content[:7] if content else None


def read_python_version(bench_path: Path) -> str | None:
    cfg = bench_path / "env" / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    try:
        text = cfg.read_text()
    except OSError:
        return None
    for line in text.splitlines():
        if line.strip().startswith("version"):
            _, _, value = line.partition("=")
            return value.strip() or None
    return None


def read_apps(bench_path: Path) -> list[AppInfo]:
    apps_dir = bench_path / "apps"
    apps_txt = bench_path / "sites" / "apps.txt"

    names: list[str] = []
    if apps_txt.is_file():
        try:
            names = [line.strip() for line in apps_txt.read_text().splitlines() if line.strip()]
        except OSError:
            names = []
    if not names and apps_dir.is_dir():
        names = sorted(d.name for d in apps_dir.iterdir() if d.is_dir())

    result: list[AppInfo] = []
    for name in names:
        app_dir = apps_dir / name
        if not app_dir.is_dir():
            continue
        result.append(
            AppInfo(
                name=name,
                version=read_app_version(app_dir),
                git_branch=read_git_branch(app_dir),
            )
        )
    return result


def read_webserver_port(bench_path: Path) -> int:
    config_path = bench_path / "sites" / "common_site_config.json"
    if not config_path.is_file():
        return DEFAULT_WEBSERVER_PORT
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_WEBSERVER_PORT
    if not isinstance(raw, dict):
        return DEFAULT_WEBSERVER_PORT
    value = raw.get("webserver_port")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return DEFAULT_WEBSERVER_PORT
        if parsed > 0:
            return parsed
    return DEFAULT_WEBSERVER_PORT


def read_sites(bench_path: Path) -> list[SiteInfo]:
    sites_dir = bench_path / "sites"
    if not sites_dir.is_dir():
        return []

    result: list[SiteInfo] = []
    for entry in sorted(sites_dir.iterdir()):
        if not entry.is_dir() or entry.name in _SITES_SKIP:
            continue
        site_config = entry / "site_config.json"
        if not site_config.is_file():
            continue

        try:
            raw = json.loads(site_config.read_text())
        except (json.JSONDecodeError, OSError):
            raw = {}
        config: dict[str, object] = raw if isinstance(raw, dict) else {}

        db_name_raw = config.get("db_name")
        db_name = db_name_raw if isinstance(db_name_raw, str) else None

        installed_apps = _read_installed_apps(entry, config)
        scheduler_paused = _truthy(config.get("pause_scheduler"))
        maintenance_mode = _truthy(config.get("maintenance_mode"))

        result.append(
            SiteInfo(
                name=entry.name,
                path=entry,
                db_name=db_name,
                installed_apps=installed_apps,
                scheduler_paused=scheduler_paused,
                maintenance_mode=maintenance_mode,
            )
        )
    return result


def _truthy(value: object) -> bool:
    # Frappe writes 1/0; some forks use booleans or "yes"/"on" strings.
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _read_installed_apps(site_dir: Path, site_config: dict[str, object]) -> list[str]:
    # Modern Frappe keeps the truth in the DB, but the file-based hints
    # cover most cases without spawning `bench --site X list-apps`.
    apps_txt = site_dir / "apps.txt"
    if apps_txt.is_file():
        try:
            from_txt = [
                line.strip() for line in apps_txt.read_text().splitlines() if line.strip()
            ]
        except OSError:
            from_txt = []
        if from_txt:
            return from_txt

    cfg_apps = site_config.get("installed_apps")
    if isinstance(cfg_apps, list):
        return [str(a) for a in cfg_apps if isinstance(a, str) and a.strip()]
    return []


def introspect(bench_path: Path) -> BenchInfo:
    apps = read_apps(bench_path)
    frappe_app = next((a for a in apps if a.name == "frappe"), None)
    return BenchInfo(
        path=bench_path.resolve(),
        frappe_version=frappe_app.version if frappe_app else None,
        python_version=read_python_version(bench_path),
        git_branch=frappe_app.git_branch if frappe_app else None,
        apps=apps,
        sites=read_sites(bench_path),
        webserver_port=read_webserver_port(bench_path),
    )
