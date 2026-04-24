from pathlib import Path

import pytest

from benchbox_core.discovery import discover_benches, is_bench


def make_fake_bench(
    path: Path,
    *,
    with_frappe: bool = True,
    with_apps_txt: bool = True,
    with_common_config: bool = True,
) -> Path:
    """Materialise a minimally bench-shaped directory tree at ``path``."""
    (path / "apps").mkdir(parents=True, exist_ok=True)
    (path / "sites").mkdir(exist_ok=True)
    (path / "env").mkdir(exist_ok=True)
    (path / "Procfile").write_text("web: bench serve\n")
    if with_frappe:
        (path / "apps" / "frappe").mkdir(exist_ok=True)
        (path / "apps" / "frappe" / "frappe").mkdir(exist_ok=True)
        (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
            '__version__ = "15.42.0"\n'
        )
    if with_apps_txt:
        (path / "sites" / "apps.txt").write_text("frappe\n")
    if with_common_config:
        (path / "sites" / "common_site_config.json").write_text("{}")
    return path


def test_is_bench_true_for_valid_shape(tmp_path: Path) -> None:
    make_fake_bench(tmp_path / "frappe-bench")
    assert is_bench(tmp_path / "frappe-bench") is True


def test_is_bench_false_for_nonexistent(tmp_path: Path) -> None:
    assert is_bench(tmp_path / "nope") is False


def test_is_bench_false_for_file(tmp_path: Path) -> None:
    f = tmp_path / "a-file"
    f.write_text("")
    assert is_bench(f) is False


def test_is_bench_false_when_apps_missing(tmp_path: Path) -> None:
    bench = make_fake_bench(tmp_path / "fb")
    import shutil

    shutil.rmtree(bench / "apps")
    assert is_bench(bench) is False


def test_is_bench_false_when_frappe_app_missing(tmp_path: Path) -> None:
    bench = make_fake_bench(tmp_path / "fb", with_frappe=False)
    assert is_bench(bench) is False


def test_is_bench_false_when_sites_has_neither_marker(tmp_path: Path) -> None:
    bench = make_fake_bench(tmp_path / "fb", with_apps_txt=False, with_common_config=False)
    assert is_bench(bench) is False


def test_is_bench_true_with_only_apps_txt(tmp_path: Path) -> None:
    bench = make_fake_bench(tmp_path / "fb", with_common_config=False)
    assert is_bench(bench) is True


def test_is_bench_true_with_only_common_config(tmp_path: Path) -> None:
    bench = make_fake_bench(tmp_path / "fb", with_apps_txt=False)
    assert is_bench(bench) is True


def test_discover_finds_single_bench(tmp_path: Path) -> None:
    make_fake_bench(tmp_path / "frappe-bench")
    result = discover_benches([tmp_path])
    assert result == [(tmp_path / "frappe-bench").resolve()]


def test_discover_finds_multiple_benches(tmp_path: Path) -> None:
    make_fake_bench(tmp_path / "a-bench")
    make_fake_bench(tmp_path / "b-bench")
    result = discover_benches([tmp_path])
    assert len(result) == 2
    assert result == sorted(result)  # sorted output


def test_discover_does_not_descend_into_a_bench(tmp_path: Path) -> None:
    outer = make_fake_bench(tmp_path / "outer-bench")
    # Simulate a weird nested-looking structure inside the bench.
    make_fake_bench(outer / "apps" / "my-custom-app")
    result = discover_benches([tmp_path])
    assert result == [outer.resolve()]


def test_discover_respects_max_depth(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "d" / "deep-bench"
    deep.parent.mkdir(parents=True)
    make_fake_bench(deep)
    assert discover_benches([tmp_path], max_depth=2) == []
    assert discover_benches([tmp_path], max_depth=5) == [deep.resolve()]


def test_discover_skips_hidden_dirs(tmp_path: Path) -> None:
    make_fake_bench(tmp_path / ".hidden" / "bench")
    (tmp_path / ".hidden" / "bench").parent.mkdir(parents=True, exist_ok=True)
    assert discover_benches([tmp_path]) == []


def test_discover_skips_node_modules(tmp_path: Path) -> None:
    make_fake_bench(tmp_path / "node_modules" / "weird-bench")
    assert discover_benches([tmp_path]) == []


def test_discover_handles_missing_path(tmp_path: Path) -> None:
    assert discover_benches([tmp_path / "does-not-exist"]) == []


def test_discover_handles_symlink_loop(tmp_path: Path) -> None:
    make_fake_bench(tmp_path / "real-bench")
    # Create a self-referential symlink — must not infinite-loop.
    (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)
    result = discover_benches([tmp_path])
    assert result == [(tmp_path / "real-bench").resolve()]


def test_discover_default_search_path_is_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    make_fake_bench(tmp_path / "home-bench")
    result = discover_benches()
    assert (tmp_path / "home-bench").resolve() in result
