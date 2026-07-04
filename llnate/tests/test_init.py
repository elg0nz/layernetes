from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from llnate.cli import app

EXPECTED_FILES = [
    "crew.py",
    "pyproject.toml",
    "Dockerfile",
    ".gitea/workflows/deploy.yaml",
    "keys.env.example",
    ".gitignore",
    "README.md",
]


def test_init_scaffolds_project(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0, result.output

    root = env / "my-agent"
    for rel in EXPECTED_FILES:
        assert (root / rel).is_file(), f"missing {rel}"

    # A git repo with an initial commit exists inside the project.
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    assert head.returncode == 0, head.stderr
    log = subprocess.run(
        ["git", "-C", str(root), "log", "--oneline"], capture_output=True, text=True
    )
    assert "llnate init" in log.stdout


def test_workflow_yaml_parses_and_uses_contract_names(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0, result.output

    raw = (env / "my-agent" / ".gitea/workflows/deploy.yaml").read_text()
    data = yaml.safe_load(raw)
    # YAML 1.1 parses a bare `on` key as boolean True.
    triggers = data.get("on", data.get(True))
    assert triggers == {"push": {"branches": ["main"]}}

    job = data["jobs"]["build-and-deploy"]
    assert job["runs-on"] == "ubuntu-latest"
    assert any("checkout" in step.get("uses", "") for step in job["steps"])

    # Contract-critical references.
    assert "${{ vars.REGISTRY }}" in raw
    assert "${{ vars.LL_API_URL }}" in raw
    assert "${{ secrets.LL_API_TOKEN }}" in raw
    assert "${{ secrets.REGISTRY_USER }}" in raw
    assert "${{ secrets.REGISTRY_PASSWORD }}" in raw
    assert "${GITHUB_SHA::7}" in raw
    assert "/v1/agents/${CR_NAME}/builds" in raw
    assert "llagent-base:latest" in raw
    # Nothing owner/repo-specific is baked in at init time.
    assert "my-agent" not in raw


def test_dockerfile_base_image_override(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0
    dockerfile = (env / "my-agent" / "Dockerfile").read_text()
    assert "ARG BASE_IMAGE=llagent-base:dev" in dockerfile
    assert "FROM ${BASE_IMAGE}" in dockerfile
    assert "COPY . /app" in dockerfile


def test_gitignore_keeps_keys_env(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0
    lines = [
        line.strip()
        for line in (env / "my-agent" / ".gitignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert ".env" in lines
    assert "keys.env" not in lines


def test_crew_py_exposes_module_level_crew(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0
    source = (env / "my-agent" / "crew.py").read_text()
    assert "crew = Crew(" in source
    compile(source, "crew.py", "exec")  # syntactically valid


def test_init_refuses_existing_directory(runner, env):
    Path("taken").mkdir()
    result = runner.invoke(app, ["init", "taken"])
    assert result.exit_code == 1


def test_plugin_install_writes_claude_md(runner, env):
    result = runner.invoke(app, ["plugin", "install"])
    assert result.exit_code == 0, result.output
    content = (env / "CLAUDE.md").read_text()
    assert "module-level `crew`" in content
    assert "https://github.com/crewAIInc/crewAI#build-with-ai" in content
