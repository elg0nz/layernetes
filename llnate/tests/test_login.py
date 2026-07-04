from __future__ import annotations

import json
import subprocess

import httpx

from llnate import config
from llnate.cli import app

from .conftest import combined_output


def _git_init(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_login_saves_config_and_configures_remote(runner, env, respx_mock, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    _git_init(project)
    monkeypatch.chdir(project)

    login_route = respx_mock.post("http://api.test/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"token": "tok-secret", "username": "gonz"})
    )
    agents_route = respx_mock.post("http://api.test/v1/agents").mock(
        return_value=httpx.Response(
            201,
            json={
                "name": "gonz-hello-agent",
                "repo": "gonz/hello-agent",
                "clone_url": "http://gitea.test:3000/gonz/hello-agent.git",
                "age_public_key": "age1testkey",
            },
        )
    )

    result = runner.invoke(app, ["login", "--username", "gonz", "--password", "pw"])
    assert result.exit_code == 0, combined_output(result)

    assert json.loads(login_route.calls.last.request.content) == {
        "username": "gonz",
        "password": "pw",
    }
    assert json.loads(agents_route.calls.last.request.content) == {"name": "hello-agent"}
    assert agents_route.calls.last.request.headers["authorization"] == "Bearer tok-secret"

    cfg = config.load()
    assert cfg["username"] == "gonz"
    assert cfg["token"] == "tok-secret"
    assert cfg["api_url"] == "http://api.test"
    assert cfg["age_public_key"] == "age1testkey"

    remote = subprocess.run(
        ["git", "remote", "get-url", "layernetes"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert remote.returncode == 0
    assert remote.stdout.strip() == "http://gonz:tok-secret@gitea.test:3000/gonz/hello-agent.git"


def test_login_replaces_existing_remote(runner, env, respx_mock, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    _git_init(project)
    monkeypatch.chdir(project)
    subprocess.run(
        ["git", "remote", "add", "layernetes", "http://old.example/x.git"],
        cwd=project,
        check=True,
    )

    respx_mock.post("http://api.test/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"token": "t2", "username": "gonz"})
    )
    respx_mock.post("http://api.test/v1/agents").mock(
        return_value=httpx.Response(
            201,
            json={
                "name": "gonz-hello-agent",
                "repo": "gonz/hello-agent",
                "clone_url": "http://gitea.test/gonz/hello-agent.git",
                "age_public_key": "age1testkey",
            },
        )
    )

    result = runner.invoke(app, ["login", "-u", "gonz", "-p", "pw"])
    assert result.exit_code == 0, combined_output(result)

    remote = subprocess.run(
        ["git", "remote", "get-url", "layernetes"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert remote.stdout.strip() == "http://gonz:t2@gitea.test/gonz/hello-agent.git"


def test_login_bad_credentials(runner, env, respx_mock, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    _git_init(project)
    monkeypatch.chdir(project)

    respx_mock.post("http://api.test/v1/auth/login").mock(
        return_value=httpx.Response(401, json={"detail": "bad credentials"})
    )
    result = runner.invoke(app, ["login", "-u", "gonz", "-p", "wrong"])
    assert result.exit_code == 1
    assert "bad credentials" in combined_output(result)
