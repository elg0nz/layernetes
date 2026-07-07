"""Project scaffolding for ``llnate init`` and ``llnate plugin install``.

Templates are kept as inline strings so the package has no data-file
packaging concerns. ``{name}``-style placeholders are filled with
``str.format``; workflow files that contain literal ``${{ ... }}`` /
``${VAR}`` syntax are written verbatim (no ``format`` call).
"""

from __future__ import annotations

from pathlib import Path

CREW_PY = '''\
"""A minimal CrewAI crew for {name}.

The Learning Layer base image (llagent-base) imports the module-level
``crew`` object from this file and serves it over FastMCP (``/mcp``) and
FastAPI (``/docs``). Keep ``crew`` defined at module level.

Model credentials are read from the environment. In the cloud they are
decrypted from ``keys.env`` in-memory at startup (``sops exec-env``);
locally, export them in your shell (e.g. ``OPENAI_API_KEY``). Nothing here
calls a model API at import time, so the module stays safe to import
without credentials.
"""

import os

from crewai import Agent, Crew, Task

# Which model to use. The API key for it (e.g. OPENAI_API_KEY) must be in
# the environment at *run* time -- add it with `llnate keys`.
MODEL = os.environ.get("LLNATE_MODEL", "gpt-4o-mini")

assistant = Agent(
    role="Helpful Assistant",
    goal="Answer the user's question clearly and concisely.",
    backstory="A pragmatic generalist who gives short, correct answers.",
    llm=MODEL,
)

answer_question = Task(
    description="Answer the following question: {{question}}",
    expected_output="A clear, concise answer to the question.",
    agent=assistant,
)

crew = Crew(agents=[assistant], tasks=[answer_question])
'''

PYPROJECT_TOML = '''\
[project]
name = "{name}"
version = "0.1.0"
description = "A CrewAI agent deployed on the Learning Layer cloud"
requires-python = ">=3.12"
dependencies = [
    "crewai",
]
'''

DOCKERFILE = '''\
# The Learning Layer base image bundles Python, pinned CrewAI, the
# FastMCP/FastAPI wrapper, sops/age, and the entrypoint that imports
# `crew` from crew.py. CI overrides BASE_IMAGE with the registry-hosted
# copy; the default targets a locally built image.
ARG BASE_IMAGE=llagent-base:dev
FROM ${BASE_IMAGE}

COPY . /app
'''

# Written verbatim -- contains ${{ ... }} and ${VAR} syntax.
DEPLOY_WORKFLOW = '''\
# Deploy pipeline scaffolded by `llnate init`.
#
# Repo configuration this workflow expects (set on the Gitea repo by ll-api
# at provisioning time):
#   vars.REGISTRY        - OCI registry host, e.g. gitea.example.com
#   vars.LL_API_URL      - ll-api base URL, e.g. https://api.layernetes.learninglayer.ai
#   secrets.LL_API_TOKEN - repo-scoped token for the ll-api builds callback
# Optional:
#   vars.BASE_IMAGE      - full ref of the llagent base image; defaults to
#     REGISTRY/llagent-base:latest (note: Gitea's registry needs an owner
#     segment in image paths, so ll-api normally sets this explicitly)
#   secrets.REGISTRY_USER / secrets.REGISTRY_PASSWORD - dedicated registry
#     credentials. If unset we fall back to `gitea.actor` + LL_API_TOKEN,
#     which assumes the repo-scoped token doubles as a Gitea access token
#     with package write scope on the built-in OCI registry.
#
# Owner/repo/CR name are derived from the runtime repository context, so
# this file is identical for every agent and never needs editing.
name: deploy

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Check out
        uses: actions/checkout@v4

      - name: Compute build metadata
        run: |
          SHORT_SHA=${GITHUB_SHA::7}
          OWNER=${GITHUB_REPOSITORY%%/*}
          REPO=${GITHUB_REPOSITORY##*/}
          {
            echo "SHORT_SHA=${SHORT_SHA}"
            echo "CR_NAME=${OWNER}-${REPO}"
            echo "IMAGE=${{ vars.REGISTRY }}/${GITHUB_REPOSITORY}:${SHORT_SHA}"
          } >> "$GITHUB_ENV"

      - name: Log in to the OCI registry
        # Not `docker login`: docker CLI >= 28 validates credentials
        # client-side with strict TLS, ignoring the daemon's
        # insecure-registry config, so plain-HTTP local registries fail.
        # Writing config.json defers auth to the daemon, which honors it.
        run: |
          if [ -n "${{ secrets.REGISTRY_USER }}" ]; then
            REG_USER="${{ secrets.REGISTRY_USER }}"
            REG_PASS="${{ secrets.REGISTRY_PASSWORD }}"
          else
            REG_USER="${{ gitea.actor }}"
            REG_PASS="${{ secrets.LL_API_TOKEN }}"
          fi
          mkdir -p ~/.docker
          AUTH=$(printf '%s:%s' "$REG_USER" "$REG_PASS" | base64 | tr -d '\\n')
          printf '{"auths": {"%s": {"auth": "%s"}}}\\n' "${{ vars.REGISTRY }}" "$AUTH" \\
            > ~/.docker/config.json

      - name: Pull base image
        # `docker pull` goes through the engine, which honors the daemon's
        # insecure-registry config. BuildKit's own resolver refuses to send
        # credentials to a plain-HTTP token endpoint, so resolving the FROM
        # remotely at build time fails on local registries — pre-pull the
        # base image and let the build use the local store.
        run: |
          BASE_IMAGE="${{ vars.BASE_IMAGE }}"
          BASE_IMAGE="${BASE_IMAGE:-${{ vars.REGISTRY }}/llagent-base:latest}"
          docker pull "$BASE_IMAGE"
          echo "BASE_IMAGE=${BASE_IMAGE}" >> "$GITHUB_ENV"

      - name: Build image
        run: docker build --build-arg "BASE_IMAGE=${BASE_IMAGE}" -t "$IMAGE" .

      - name: Push image
        run: docker push "$IMAGE"

      - name: Report build to ll-api
        run: |
          curl -sf -X POST "${{ vars.LL_API_URL }}/v1/agents/${CR_NAME}/builds" \
            -H "Authorization: Bearer ${{ secrets.LL_API_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d "{\\"sha\\":\\"${SHORT_SHA}\\",\\"image\\":\\"${IMAGE}\\"}"
'''

KEYS_ENV_EXAMPLE = '''\
# Example credentials for your agent. Do NOT put real values in this file.
# Run `llnate keys` to encrypt real credentials into keys.env (safe to
# commit -- it is sops/age encrypted; only your running agent can read it).
OPENAI_API_KEY=sk-replace-me
'''

GITIGNORE = '''\
# Plaintext secrets must never be committed.
.env
*.env.plaintext

# NOTE: keys.env is intentionally NOT ignored -- it is sops/age encrypted
# and is meant to be committed alongside your code.

__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
'''

PROJECT_README = '''\
# {name}

This is a [CrewAI](https://github.com/crewAIInc/crewAI) agent scaffolded by
`llnate init`. Build it with your coding assistant: run `llnate plugin
install` to wire up CrewAI's "Build with AI" hooks, then iterate on
`crew.py` -- the only rule is that it must keep exposing a module-level
`crew` object, which the Learning Layer base image serves over MCP
(`/mcp`) and HTTP (`/docs`).

When you are ready to ship: `llnate login` provisions your cloud repo and
age encryption key, `llnate keys` encrypts your credentials (model API
keys, etc.) into a committable `keys.env`, and `llnate push` deploys --
it streams build/deploy progress and prints your agent's public MCP and
HTTP URLs when it goes live.
'''

CLAUDE_MD = '''\
# Building this LLAgent

This project is a CrewAI agent deployed on the Learning Layer cloud.
Guidance for AI coding assistants working in this repo:

## Hard requirements

- `crew.py` MUST expose a module-level `crew` object (a `crewai.Crew`).
  The deployment base image imports `crew` from `crew.py` and serves it
  over FastMCP (`/mcp`) and FastAPI (`/docs`) on port 8000. Renaming or
  nesting it inside a function breaks deployment.
- Do not perform network calls or require credentials at import time.
  Credentials arrive via the environment at runtime (decrypted in-memory
  from keys.env by `sops exec-env`).
- Never write plaintext secrets to the repo. `keys.env` is encrypted
  (managed by `llnate keys`); `.env` is gitignored for local use.

## How to extend the crew

- Add agents: create more `crewai.Agent` instances and list them in
  `Crew(agents=[...])`.
- Add tasks: create `crewai.Task` instances (description, expected_output,
  agent) and list them in `Crew(tasks=[...])`.
- Add tools: give agents `tools=[...]` using `crewai` tools or the
  `crewai_tools` package (add it to pyproject.toml dependencies).
- Task inputs use `{placeholder}` template variables; callers supply them
  at kickoff.

## References

- CrewAI "Build with AI": https://github.com/crewAIInc/crewAI#build-with-ai
- CrewAI docs: https://docs.crewai.com/
'''


def project_files(name: str) -> dict[str, str]:
    """Relative path -> content for a new agent project."""
    return {
        "crew.py": CREW_PY.format(name=name),
        "pyproject.toml": PYPROJECT_TOML.format(name=name),
        "Dockerfile": DOCKERFILE,
        ".gitea/workflows/deploy.yaml": DEPLOY_WORKFLOW,
        "keys.env.example": KEYS_ENV_EXAMPLE,
        ".gitignore": GITIGNORE,
        "README.md": PROJECT_README.format(name=name),
    }


def create_project(root: Path, name: str) -> list[Path]:
    """Write the scaffold under ``root``. Returns the created file paths."""
    created = []
    for rel, content in project_files(name).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created
