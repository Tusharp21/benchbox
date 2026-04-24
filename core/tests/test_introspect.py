import json
from pathlib import Path

from benchbox_core.introspect import (
    DEFAULT_WEBSERVER_PORT,
    AppInfo,
    SiteInfo,
    introspect,
    read_app_version,
    read_apps,
    read_git_branch,
    read_python_version,
    read_sites,
    read_webserver_port,
)


def _make_app(
    apps_dir: Path,
    name: str,
    *,
    version: str | None = None,
    branch: str | None = None,
) -> None:
    app = apps_dir / name
    inner = app / name
    inner.mkdir(parents=True, exist_ok=True)
    if version is not None:
        inner.joinpath("__init__.py").write_text(f'__version__ = "{version}"\n')
    else:
        inner.joinpath("__init__.py").write_text("# no version\n")
    if branch is not None:
        git_dir = app / ".git"
        git_dir.mkdir(exist_ok=True)
        git_dir.joinpath("HEAD").write_text(f"ref: refs/heads/{branch}\n")


def _make_site(
    sites_dir: Path,
    name: str,
    *,
    db_name: str | None = "db_abc123",
    installed_apps: list[str] | None = None,
) -> None:
    site = sites_dir / name
    site.mkdir(parents=True, exist_ok=True)
    config: dict[str, object] = {}
    if db_name is not None:
        config["db_name"] = db_name
    site.joinpath("site_config.json").write_text(json.dumps(config))
    if installed_apps is not None:
        site.joinpath("apps.txt").write_text("\n".join(installed_apps) + "\n")


def _make_bench(
    root: Path,
    *,
    apps_in_order: list[str] | None = None,
    python_version: str | None = "3.10.12",
) -> Path:
    (root / "apps").mkdir(parents=True, exist_ok=True)
    (root / "sites").mkdir(exist_ok=True)
    (root / "env").mkdir(exist_ok=True)
    if apps_in_order is not None:
        (root / "sites" / "apps.txt").write_text("\n".join(apps_in_order) + "\n")
    if python_version is not None:
        (root / "env" / "pyvenv.cfg").write_text(f"home = /usr/bin\nversion = {python_version}\n")
    return root


def test_read_app_version_happy_path(tmp_path: Path) -> None:
    _make_app(tmp_path, "frappe", version="15.42.0")
    assert read_app_version(tmp_path / "frappe") == "15.42.0"


def test_read_app_version_missing_file(tmp_path: Path) -> None:
    (tmp_path / "frappe").mkdir()
    assert read_app_version(tmp_path / "frappe") is None


def test_read_app_version_no_version_attr(tmp_path: Path) -> None:
    _make_app(tmp_path, "frappe")  # no version
    assert read_app_version(tmp_path / "frappe") is None


def test_read_app_version_handles_syntax_error(tmp_path: Path) -> None:
    app = tmp_path / "broken"
    (app / "broken").mkdir(parents=True)
    (app / "broken" / "__init__.py").write_text("this is :: not valid python")
    assert read_app_version(app) is None


def test_read_git_branch_ref(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    git.joinpath("HEAD").write_text("ref: refs/heads/version-15\n")
    assert read_git_branch(tmp_path) == "version-15"


def test_read_git_branch_detached(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    git.joinpath("HEAD").write_text("abcdef1234567890" * 2 + "\n")
    result = read_git_branch(tmp_path)
    assert result == "abcdef1"


def test_read_git_branch_missing(tmp_path: Path) -> None:
    assert read_git_branch(tmp_path) is None


def test_read_python_version(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path, python_version="3.11.7")
    assert read_python_version(bench) == "3.11.7"


def test_read_python_version_missing_cfg(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path, python_version=None)
    assert read_python_version(bench) is None


def test_read_apps_ordered_by_apps_txt(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path, apps_in_order=["frappe", "erpnext", "hrms"])
    _make_app(bench / "apps", "frappe", version="15.1", branch="version-15")
    _make_app(bench / "apps", "erpnext", version="15.2", branch="version-15")
    _make_app(bench / "apps", "hrms", version="15.3", branch="develop")
    apps = read_apps(bench)
    assert [a.name for a in apps] == ["frappe", "erpnext", "hrms"]
    assert apps[0] == AppInfo("frappe", "15.1", "version-15")
    assert apps[2] == AppInfo("hrms", "15.3", "develop")


def test_read_apps_falls_back_to_filesystem_order(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path, apps_in_order=None)
    _make_app(bench / "apps", "zed", version="1.0")
    _make_app(bench / "apps", "alpha", version="2.0")
    apps = read_apps(bench)
    assert [a.name for a in apps] == ["alpha", "zed"]


def test_read_apps_skips_names_without_app_dir(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path, apps_in_order=["frappe", "ghost"])
    _make_app(bench / "apps", "frappe", version="15.1")
    # ghost is listed in apps.txt but has no apps/ghost dir
    apps = read_apps(bench)
    assert [a.name for a in apps] == ["frappe"]


def test_read_sites(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path)
    _make_site(
        bench / "sites", "site1.local", db_name="db_abc", installed_apps=["frappe", "erpnext"]
    )
    _make_site(bench / "sites", "site2.local", db_name="db_xyz")
    sites = read_sites(bench)
    assert [s.name for s in sites] == ["site1.local", "site2.local"]
    assert sites[0].db_name == "db_abc"
    assert sites[0].installed_apps == ["frappe", "erpnext"]
    assert sites[1].installed_apps == []


def test_read_sites_skips_assets_dir(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path)
    (bench / "sites" / "assets").mkdir()
    (bench / "sites" / "assets" / "site_config.json").write_text("{}")
    _make_site(bench / "sites", "real.local")
    sites = read_sites(bench)
    assert [s.name for s in sites] == ["real.local"]


def test_read_sites_skips_dirs_without_site_config(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path)
    (bench / "sites" / "not-a-site").mkdir()
    _make_site(bench / "sites", "real.local")
    assert [s.name for s in read_sites(bench)] == ["real.local"]


def test_read_sites_tolerates_malformed_json(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path)
    site = bench / "sites" / "broken.local"
    site.mkdir(parents=True)
    site.joinpath("site_config.json").write_text("{ not valid json")
    sites = read_sites(bench)
    assert len(sites) == 1
    assert sites[0].db_name is None


def test_introspect_end_to_end(tmp_path: Path) -> None:
    bench = _make_bench(
        tmp_path / "my-bench",
        apps_in_order=["frappe", "erpnext"],
        python_version="3.11.7",
    )
    _make_app(bench / "apps", "frappe", version="15.42.0", branch="version-15")
    _make_app(bench / "apps", "erpnext", version="15.38.1", branch="version-15")
    _make_site(bench / "sites", "one.local", db_name="db_one", installed_apps=["frappe"])

    info = introspect(bench)

    assert info.path == bench.resolve()
    assert info.frappe_version == "15.42.0"
    assert info.python_version == "3.11.7"
    assert info.git_branch == "version-15"
    assert [a.name for a in info.apps] == ["frappe", "erpnext"]
    assert [s.name for s in info.sites] == ["one.local"]
    assert info.sites[0].installed_apps == ["frappe"]


def test_introspect_missing_frappe_is_tolerated(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path / "weird", apps_in_order=["custom_app"])
    _make_app(bench / "apps", "custom_app", version="0.1")
    info = introspect(bench)
    assert info.frappe_version is None
    assert info.git_branch is None
    assert [a.name for a in info.apps] == ["custom_app"]


def test_read_webserver_port_defaults_when_config_missing(tmp_path: Path) -> None:
    # No common_site_config.json at all.
    assert read_webserver_port(tmp_path) == DEFAULT_WEBSERVER_PORT


def test_read_webserver_port_defaults_when_key_missing(tmp_path: Path) -> None:
    sites = tmp_path / "sites"
    sites.mkdir()
    (sites / "common_site_config.json").write_text(json.dumps({"other": "value"}))
    assert read_webserver_port(tmp_path) == DEFAULT_WEBSERVER_PORT


def test_read_webserver_port_honours_int_in_config(tmp_path: Path) -> None:
    sites = tmp_path / "sites"
    sites.mkdir()
    (sites / "common_site_config.json").write_text(json.dumps({"webserver_port": 8001}))
    assert read_webserver_port(tmp_path) == 8001


def test_read_webserver_port_parses_string_port(tmp_path: Path) -> None:
    # Frappe sometimes writes numeric values as strings (config-set via CLI).
    sites = tmp_path / "sites"
    sites.mkdir()
    (sites / "common_site_config.json").write_text(json.dumps({"webserver_port": "8002"}))
    assert read_webserver_port(tmp_path) == 8002


def test_read_webserver_port_falls_back_on_malformed_json(tmp_path: Path) -> None:
    sites = tmp_path / "sites"
    sites.mkdir()
    (sites / "common_site_config.json").write_text("{not json")
    assert read_webserver_port(tmp_path) == DEFAULT_WEBSERVER_PORT


def test_introspect_surfaces_webserver_port(tmp_path: Path) -> None:
    bench = _make_bench(tmp_path / "b", apps_in_order=["frappe"])
    _make_app(bench / "apps", "frappe", version="15.0.0", branch="version-15")
    (bench / "sites" / "common_site_config.json").write_text(
        json.dumps({"webserver_port": 8123})
    )
    info = introspect(bench)
    assert info.webserver_port == 8123


def test_siteinfo_and_appinfo_are_frozen() -> None:
    # Sanity: the dataclasses are immutable so GUI layer can safely cache them.
    app = AppInfo(name="frappe", version="15.0", git_branch="main")
    site = SiteInfo(name="s.local", path=Path("/tmp/s"), db_name=None, installed_apps=[])
    try:
        app.name = "changed"  # type: ignore[misc]
    except Exception:  # noqa: BLE001
        pass
    else:
        raise AssertionError("AppInfo should be frozen")
    try:
        site.name = "changed"  # type: ignore[misc]
    except Exception:  # noqa: BLE001
        pass
    else:
        raise AssertionError("SiteInfo should be frozen")
