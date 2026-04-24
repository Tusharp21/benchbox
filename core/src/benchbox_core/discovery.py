"""Find existing Frappe benches on disk.

A Frappe bench is a directory with roughly this shape::

    frappe-bench/
      apps/
        frappe/          <- must be present; it's what makes a bench a bench
        erpnext/
        ...
      sites/
        apps.txt         <- or common_site_config.json
        common_site_config.json
        site1.local/
      env/
      Procfile

We recognise a bench by the presence of ``apps/frappe/`` plus a populated
``sites/`` dir. That's stricter than "has an apps folder" (which would match
any random project) and cheaper than parsing ``apps.txt``.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_DEPTH: int = 3

# Directory names we never descend into when searching — fast-path skips that
# also avoid accidentally walking into massive caches or vendored trees.
_SKIP_NAMES: frozenset[str] = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "target",
        ".cache",
        ".npm",
        ".cargo",
        ".rustup",
        ".pyenv",
        ".nvm",
        ".local",
        "snap",
    }
)


def is_bench(path: Path) -> bool:
    """Return True if ``path`` looks like a Frappe bench directory."""
    if not path.is_dir():
        return False
    apps_dir = path / "apps"
    sites_dir = path / "sites"
    if not apps_dir.is_dir() or not sites_dir.is_dir():
        return False
    if not (apps_dir / "frappe").is_dir():
        return False
    has_apps_txt = (sites_dir / "apps.txt").is_file()
    has_common_config = (sites_dir / "common_site_config.json").is_file()
    return has_apps_txt or has_common_config


def discover_benches(
    search_paths: list[Path] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[Path]:
    """Scan for Frappe benches rooted under ``search_paths``.

    Defaults to the user's home directory. Returned paths are resolved
    (absolute, symlinks dereferenced) and sorted for stable output.
    """
    if search_paths is None:
        search_paths = [Path.home()]

    found: set[Path] = set()
    visited: set[Path] = set()
    for start in search_paths:
        _scan(start.expanduser(), max_depth, found, visited)
    return sorted(found)


def _scan(current: Path, depth_remaining: int, found: set[Path], visited: set[Path]) -> None:
    try:
        resolved = current.resolve()
    except OSError:
        return
    if resolved in visited:
        return
    visited.add(resolved)

    if not current.is_dir():
        return

    if is_bench(current):
        found.add(resolved)
        return  # Don't descend into a bench — apps/frappe has its own tree.

    if depth_remaining <= 0:
        return

    try:
        children = list(current.iterdir())
    except (PermissionError, OSError):
        return

    for child in children:
        if child.is_symlink():
            continue
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name in _SKIP_NAMES:
            continue
        _scan(child, depth_remaining - 1, found, visited)
