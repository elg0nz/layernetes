from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated cwd, config dir, and API URL for every test."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LLNATE_API_URL", "http://api.test")
    monkeypatch.delenv("LLNATE_USERNAME", raising=False)
    monkeypatch.delenv("LLNATE_PASSWORD", raising=False)
    return tmp_path


@pytest.fixture
def stub_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory prepended to PATH for stubbing binaries (git, sops)."""
    directory = tmp_path / "stub-bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return directory


def write_stub(directory: Path, name: str, body: str) -> Path:
    """Create an executable POSIX-sh stub script."""
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def combined_output(result) -> str:
    output = result.output
    try:
        output += result.stderr
    except (ValueError, AttributeError):
        pass
    return output


def logged_in_config() -> dict:
    from llnate import config

    return config.update(
        api_url="http://api.test",
        username="gonz",
        token="tok-secret",
        age_public_key="age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p",
    )
