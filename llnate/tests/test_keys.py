from __future__ import annotations

import tempfile
from pathlib import Path

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


def _leftover_tempfiles() -> list[Path]:
    return list(Path(tempfile.gettempdir()).glob("llnate-keys-*"))


def test_keys_encrypts_pairs(runner, env, stub_bin):
    logged_in_config()
    write_stub(stub_bin, "sops", SOPS_OK)

    result = runner.invoke(app, ["keys", "OPENAI_API_KEY=sk-123", "OTHER=x"])
    assert result.exit_code == 0, combined_output(result)

    keys_env = (env / "keys.env").read_text()
    assert "ENC:OPENAI_API_KEY=sk-123" in keys_env
    assert "ENC:OTHER=x" in keys_env

    sops_yaml = (env / ".sops.yaml").read_text()
    assert "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p" in sops_yaml
    assert "dotenv" in sops_yaml

    assert _leftover_tempfiles() == []


def test_keys_interactive_prompts(runner, env, stub_bin):
    logged_in_config()
    write_stub(stub_bin, "sops", SOPS_OK)

    result = runner.invoke(app, ["keys"], input="FOO=bar\n\n")
    assert result.exit_code == 0, combined_output(result)
    assert "ENC:FOO=bar" in (env / "keys.env").read_text()


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
