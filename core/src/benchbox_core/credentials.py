"""Local credential store at ~/.benchbox/credentials.json (0600)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

DEFAULT_CONFIG_DIR: Path = Path.home() / ".benchbox"
ENV_CONFIG_DIR: str = "BENCHBOX_CONFIG_DIR"
_CREDENTIALS_FILENAME: str = "credentials.json"

MARIADB_ROOT_PASSWORD_KEY: str = "mariadb_root_password"


def config_dir() -> Path:
    override = os.environ.get(ENV_CONFIG_DIR)
    return Path(override) if override else DEFAULT_CONFIG_DIR


def credentials_path() -> Path:
    return config_dir() / _CREDENTIALS_FILENAME


def _load() -> dict[str, str]:
    path = credentials_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def _save(data: dict[str, str]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def get(key: str) -> str | None:
    return _load().get(key)


def set_(key: str, value: str) -> None:
    data = _load()
    data[key] = value
    _save(data)


def unset(key: str) -> bool:
    data = _load()
    if key not in data:
        return False
    del data[key]
    _save(data)
    return True


def get_mariadb_root_password() -> str | None:
    return get(MARIADB_ROOT_PASSWORD_KEY)


def set_mariadb_root_password(password: str) -> None:
    set_(MARIADB_ROOT_PASSWORD_KEY, password)
