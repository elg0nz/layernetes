from __future__ import annotations

import httpx

from llnate.cli import app

from .conftest import combined_output, logged_in_config


def _setup_project(env, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    monkeypatch.chdir(project)
    logged_in_config()
    return project


def test_status_ready(runner, env, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        return_value=httpx.Response(
            200,
            json={
                "phase": "Ready",
                "url": "https://3f2a91c.agents.learninglayer.ai",
                "message": "",
            },
        )
    )
    result = runner.invoke(app, ["status"])
    output = combined_output(result)
    assert result.exit_code == 0, output
    assert "gonz-hello-agent: Ready" in output
    assert "https://3f2a91c.agents.learninglayer.ai/mcp" in output


def test_status_failed_exits_nonzero(runner, env, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        return_value=httpx.Response(
            200, json={"phase": "Failed", "url": "", "message": "crash loop"}
        )
    )
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "crash loop" in combined_output(result)


def test_delete_with_yes(runner, env, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    route = respx_mock.delete("http://api.test/v1/agents/gonz-hello-agent").mock(
        return_value=httpx.Response(204)
    )
    result = runner.invoke(app, ["delete", "--yes"])
    assert result.exit_code == 0, combined_output(result)
    assert route.call_count == 1
    assert route.calls.last.request.headers["authorization"] == "Bearer tok-secret"


def test_delete_confirmation_declined(runner, env, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    route = respx_mock.delete("http://api.test/v1/agents/gonz-hello-agent").mock(
        return_value=httpx.Response(204)
    )
    result = runner.invoke(app, ["delete"], input="n\n")
    assert result.exit_code != 0
    assert route.call_count == 0


def test_delete_confirmation_accepted(runner, env, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    route = respx_mock.delete("http://api.test/v1/agents/gonz-hello-agent").mock(
        return_value=httpx.Response(204)
    )
    result = runner.invoke(app, ["delete"], input="y\n")
    assert result.exit_code == 0, combined_output(result)
    assert route.call_count == 1


def test_delete_api_error(runner, env, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    respx_mock.delete("http://api.test/v1/agents/gonz-hello-agent").mock(
        return_value=httpx.Response(404, json={"detail": "agent not found"})
    )
    result = runner.invoke(app, ["delete", "--yes"])
    assert result.exit_code == 1
    assert "agent not found" in combined_output(result)
