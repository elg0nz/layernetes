"""Project-local identity: ``.llnate.toml`` in the project root.

Unlike ``~/.config/llnate/config.toml`` (one login session, shared across
every project on the machine), this file pins *this* project's LLAgent CR
name. ``push``/``status``/``delete`` read it so they don't have to re-derive
the name from the current directory's name, which breaks if the directory is
renamed -- or, disaster-recovery case: if the local clone is lost entirely,
hand-write ``.llnate.toml`` with the right ``agent_name``, ``llnate login``
as the owning (or admin) user, and they resolve correctly again. Gitignored
by the scaffold since it's just a local pointer, not project source.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


def path() -> Path:
    return Path.cwd() / ".llnate.toml"


def load() -> dict:
    p = path()
    if not p.exists():
        return {}
    with p.open("rb") as fh:
        return tomllib.load(fh)


def save(**kwargs) -> None:
    data = load()
    data.update(kwargs)
    lines = [f"{key} = {json.dumps(value)}" for key, value in data.items() if value is not None]
    path().write_text("\n".join(lines) + "\n", encoding="utf-8")
