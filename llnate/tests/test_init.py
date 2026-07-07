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
    "AGENTS.md",
    "CLAUDE.md",
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
    assert "class AssistantCrew(Crew):" in source
    assert "crew = AssistantCrew(" in source
    assert "@@NAME@@" not in source  # name placeholder was substituted
    compile(source, "crew.py", "exec")  # syntactically valid


def test_crew_py_normalizes_caller_input(runner, env, monkeypatch):
    """The scaffolded crew coerces any caller payload to a non-empty question,
    so the `{question}` template can never crash interpolation (AGENTS.md §3)."""
    import importlib.util
    import sys
    import types

    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0, result.output

    # Stub crewai so crew.py imports without the real (heavy) package. The
    # stub Crew.kickoff echoes back the inputs it received, letting us observe
    # exactly what AssistantCrew normalized the caller's payload to.
    crewai = types.ModuleType("crewai")

    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

    class Crew(_Stub):
        def kickoff(self, inputs=None, input_files=None, from_checkpoint=None):
            return inputs

    crewai.Agent = _Stub
    crewai.Task = _Stub
    crewai.Crew = Crew
    monkeypatch.setitem(sys.modules, "crewai", crewai)

    path = env / "my-agent" / "crew.py"
    spec = importlib.util.spec_from_file_location("scaffolded_crew", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # constructs Agent/Task/AssistantCrew

    kick = module.crew.kickoff
    # Exact key passes through untouched.
    assert kick({"question": "What is 2+2?"})["question"] == "What is 2+2?"
    # A differently-keyed payload (the old trap) is mapped, not crashed.
    assert kick({"topic": "hello"})["question"] == "hello"
    # A single unknown key still yields its value as the question.
    assert kick({"foo": "bar"})["question"] == "bar"
    # Empty / missing input falls back to a non-empty default.
    assert kick({})["question"]
    assert kick(None)["question"]


def test_agents_md_covers_the_contract_and_llnate_usage(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0, result.output
    agents = (env / "my-agent" / "AGENTS.md").read_text()

    # The one hard runtime rule.
    assert "module-level" in agents
    assert "crew.kickoff(inputs=inputs)" in agents
    # Version pins match the base image (llagent-base/Dockerfile).
    assert "crewai 1.15.1" in agents
    # "how to use llnate" -- the developer-loop commands are documented.
    for command in ("llnate login", "llnate keys", "llnate push", "llnate status"):
        assert command in agents, f"AGENTS.md should document `{command}`"
    # The input convention the scaffold now implements is documented.
    assert "AssistantCrew" in agents
    assert "_coerce_question" in agents
    # No monorepo-only path leaked in from the template draft.
    assert "~/Code/layernetes" not in agents


def test_init_refuses_existing_directory(runner, env):
    Path("taken").mkdir()
    result = runner.invoke(app, ["init", "taken"])
    assert result.exit_code == 1


def test_init_writes_claude_md_pointing_at_agents_md(runner, env):
    result = runner.invoke(app, ["init", "my-agent"])
    assert result.exit_code == 0, result.output
    content = (env / "my-agent" / "CLAUDE.md").read_text()
    assert "AGENTS.md" in content


def test_plugin_install_writes_claude_md(runner, env):
    result = runner.invoke(app, ["plugin", "install"])
    assert result.exit_code == 0, result.output
    content = (env / "CLAUDE.md").read_text()
    # CLAUDE.md is a thin pointer at the real guidance in AGENTS.md.
    assert "AGENTS.md" in content
