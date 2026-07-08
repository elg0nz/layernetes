from __future__ import annotations

import tempfile
from pathlib import Path

import httpx

from llnate.cli import app

from .conftest import combined_output, logged_in_config, write_stub

# Emulates `sops --encrypt ... <file>`: prints the last argument's content
# with each line prefixed by ENC:.
SOPS_OK = """\
for last; do :; done
sed 's/^/ENC:/' "$last"
"""

SOPS_FAIL = """\
echo "sops boom" >&2
exit 1
"""

# `keys` now commits and pushes (`llnate push`) after encrypting, so its
# success tests stub `git` the same way test_push.py does.
GIT_OK = """\
echo "stub-git $@"
exit 0
"""


def _mock_ready_status(respx_mock) -> None:
    respx_mock.get("http://api.test/v1/agents/gonz-hello-agent/status").mock(
        return_value=httpx.Response(200, json={"phase": "Ready", "url": "https://x.agents.test"})
    )


def _leftover_tempfiles() -> list[Path]:
    return list(Path(tempfile.gettempdir()).glob("llnate-keys-*"))


def test_keys_encrypts_pairs(runner, env, stub_bin, respx_mock, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    monkeypatch.chdir(project)
    logged_in_config()
    write_stub(stub_bin, "sops", SOPS_OK)
    write_stub(stub_bin, "git", GIT_OK)
    _mock_ready_status(respx_mock)

    result = runner.invoke(app, ["keys", "OPENAI_API_KEY=sk-123", "OTHER=x"])
    assert result.exit_code == 0, combined_output(result)

    keys_env = (project / "keys.env").read_text()
    assert "ENC:OPENAI_API_KEY=sk-123" in keys_env
    assert "ENC:OTHER=x" in keys_env

    sops_yaml = (project / ".sops.yaml").read_text()
    assert "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p" in sops_yaml
    assert "dotenv" in sops_yaml

    output = combined_output(result)
    assert "Committed keys.env" in output
    assert "HTTP: https://x.agents.test" in output
    assert "curl -s -X POST https://x.agents.test/kickoff" in output
    assert "claude mcp add --transport http agent https://x.agents.test/mcp" in output
    assert _leftover_tempfiles() == []


def test_keys_interactive_prompts(runner, env, stub_bin, respx_mock, monkeypatch):
    project = env / "hello-agent"
    project.mkdir()
    monkeypatch.chdir(project)
    logged_in_config()
    write_stub(stub_bin, "sops", SOPS_OK)
    write_stub(stub_bin, "git", GIT_OK)
    _mock_ready_status(respx_mock)

    result = runner.invoke(app, ["keys"], input="FOO=bar\n\n")
    assert result.exit_code == 0, combined_output(result)
    assert "ENC:FOO=bar" in (project / "keys.env").read_text()


def test_keys_cleans_up_plaintext_on_sops_failure(runner, env, stub_bin):
    logged_in_config()
    write_stub(stub_bin, "sops", SOPS_FAIL)

    result = runner.invoke(app, ["keys", "FOO=bar"])
    assert result.exit_code == 1
    assert "sops" in combined_output(result)
    assert not (env / "keys.env").exists()
    assert _leftover_tempfiles() == []


def test_keys_requires_sops_binary(runner, env, stub_bin, monkeypatch):
    logged_in_config()
    # PATH contains only the (empty) stub dir: no sops anywhere.
    monkeypatch.setenv("PATH", str(stub_bin))

    result = runner.invoke(app, ["keys", "FOO=bar"])
    assert result.exit_code == 1
    assert "sops" in combined_output(result)


def test_keys_rejects_malformed_pair(runner, env, stub_bin):
    logged_in_config()
    write_stub(stub_bin, "sops", SOPS_OK)

    result = runner.invoke(app, ["keys", "NOT-A-PAIR"])
    assert result.exit_code == 1
    assert not (env / "keys.env").exists()


def test_keys_requires_login(runner, env, stub_bin):
    write_stub(stub_bin, "sops", SOPS_OK)
    result = runner.invoke(app, ["keys", "FOO=bar"])
    assert result.exit_code == 1
    assert "login" in combined_output(result)
