from __future__ import annotations

import httpx

from llnate.cli import app

from .conftest import combined_output, logged_in_config, write_stub

GIT_OK = """\
echo "stub-git $@"
exit 0
"""

GIT_FAIL = """\
echo "stub-git refusing" >&2
exit 1
"""


def _setup_project(env, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    monkeypatch.chdir(project)
    logged_in_config()
    return project


def test_push_streams_transitions_until_ready(runner, env, stub_bin, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    write_stub(stub_bin, "git", GIT_OK)
    monkeypatch.setattr("llnate.cli.time.sleep", lambda seconds: None)

    status_route = respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        side_effect=[
            httpx.Response(200, json={"phase": "Pending", "url": "", "message": ""}),
            httpx.Response(200, json={"phase": "Deploying", "url": "", "message": ""}),
            httpx.Response(
                200,
                json={
                    "phase": "Ready",
                    "url": "https://3f2a91c.agents.learninglayer.ai",
                    "message": "",
                },
            ),
        ]
    )

    result = runner.invoke(app, ["push"])
    output = combined_output(result)
    assert result.exit_code == 0, output
    assert status_route.call_count == 3
    assert "phase: Pending" in output
    assert "phase: Deploying" in output
    assert "phase: Ready" in output
    assert "HTTP: https://3f2a91c.agents.learninglayer.ai" in output
    assert "MCP:  https://3f2a91c.agents.learninglayer.ai/mcp" in output
    assert "Docs: https://3f2a91c.agents.learninglayer.ai/docs" in output


def test_push_failed_deploy_exits_nonzero(runner, env, stub_bin, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    write_stub(stub_bin, "git", GIT_OK)
    monkeypatch.setattr("llnate.cli.time.sleep", lambda seconds: None)
    # No stale-failure grace: a Failed as the first observed phase is final.
    monkeypatch.setattr("llnate.cli.STALE_FAILURE_GRACE_SECONDS", 0)

    respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        return_value=httpx.Response(
            200, json={"phase": "Failed", "url": "", "message": "image pull backoff"}
        )
    )

    result = runner.invoke(app, ["push"])
    assert result.exit_code == 1
    assert "image pull backoff" in combined_output(result)


def test_push_waits_out_stale_failed_status(runner, env, stub_bin, respx_mock, monkeypatch):
    """A Failed left over from the previous revision must not be read as
    this deploy's outcome while CI hasn't reported the new sha yet."""
    _setup_project(env, monkeypatch)
    write_stub(stub_bin, "git", GIT_OK)
    monkeypatch.setattr("llnate.cli.time.sleep", lambda seconds: None)

    respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        side_effect=[
            httpx.Response(200, json={"phase": "Failed", "url": "", "message": "old failure"}),
            httpx.Response(200, json={"phase": "Failed", "url": "", "message": "old failure"}),
            httpx.Response(200, json={"phase": "Deploying", "url": "", "message": ""}),
            httpx.Response(
                200,
                json={"phase": "Ready", "url": "https://abc1234.agents.test", "message": ""},
            ),
        ]
    )

    result = runner.invoke(app, ["push"])
    output = combined_output(result)
    assert result.exit_code == 0, output
    assert "previous revision had failed" in output
    assert "old failure" not in output.replace("previous revision had failed", "")
    assert "HTTP: https://abc1234.agents.test" in output


def test_push_git_failure_aborts_before_polling(runner, env, stub_bin, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    write_stub(stub_bin, "git", GIT_FAIL)

    status_route = respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        return_value=httpx.Response(200, json={"phase": "Ready", "url": "x", "message": ""})
    )

    result = runner.invoke(app, ["push"])
    assert result.exit_code == 1
    assert "git push failed" in combined_output(result)
    assert status_route.call_count == 0


def test_push_times_out(runner, env, stub_bin, respx_mock, monkeypatch):
    _setup_project(env, monkeypatch)
    write_stub(stub_bin, "git", GIT_OK)
    monkeypatch.setattr("llnate.cli.time.sleep", lambda seconds: None)

    # Advance a fake clock 2s per poll; time out after ~15 simulated minutes.
    clock = {"now": 0.0}

    def fake_monotonic():
        clock["now"] += 1.0
        return clock["now"]

    monkeypatch.setattr("llnate.cli.time.monotonic", fake_monotonic)

    respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        return_value=httpx.Response(200, json={"phase": "Deploying", "url": "", "message": ""})
    )

    result = runner.invoke(app, ["push"])
    assert result.exit_code == 1
    assert "timed out" in combined_output(result)


def test_push_requires_login(runner, env, stub_bin):
    write_stub(stub_bin, "git", GIT_OK)
    result = runner.invoke(app, ["push"])
    assert result.exit_code == 1
    assert "login" in combined_output(result)
