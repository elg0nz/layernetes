"""Configuration and token storage for llnate.

Config lives at ``$XDG_CONFIG_HOME/llnate/config.toml`` (defaulting to
``~/.config/llnate/config.toml``). The API URL is resolved as:

1. ``LLNATE_API_URL`` environment variable
2. ``api_url`` in the config file
3. ``https://api.learninglayer.ai``
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

DEFAULT_API_URL = "https://api.learninglayer.ai"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "llnate"


def config_path() -> Path:
    return config_dir() / "config.toml"


def load() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def save(data: dict) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in data.items():
        if value is None:
            continue
        # json string escaping is a valid TOML basic-string encoding.
        lines.append(f"{key} = {json.dumps(value)}")
    path = config_path()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)  # the file holds the API token


def update(**kwargs) -> dict:
    data = load()
    data.update(kwargs)
    save(data)
    return data


def api_url() -> str:
    env = os.environ.get("LLNATE_API_URL")
    if env:
        return env.rstrip("/")
    configured = load().get("api_url")
    return (configured or DEFAULT_API_URL).rstrip("/")
