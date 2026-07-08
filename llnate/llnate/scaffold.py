"""Project scaffolding for ``llnate init`` and ``llnate plugin install``.

Templates are kept as inline strings so the package has no data-file
packaging concerns. ``{name}``-style placeholders are filled with
``str.format``; workflow files that contain literal ``${{ ... }}`` /
``${VAR}`` syntax are written verbatim (no ``format`` call).
"""

from __future__ import annotations

from pathlib import Path

# Written verbatim -- the body has literal `{}` (dict literals, the
# `{question}` template var), so it must NOT go through str.format. The
# project name is substituted with a plain str.replace of @@NAME@@.
CREW_PY = '''\
"""A minimal CrewAI crew for @@NAME@@.

The Learning Layer base image (llagent-base) imports the module-level
``crew`` object from this file and serves it over FastMCP (``/mcp``) and
FastAPI (``/docs``). Keep ``crew`` defined at module level.

Model credentials are read from the environment. In the cloud they are
decrypted from ``keys.env`` in-memory at startup (``sops exec-env``);
locally, export them in your shell (e.g. ``OPENAI_API_KEY``). Nothing here
calls a model API at import time, so the module stays safe to import
without credentials.

Input convention
----------------
This crew answers a single **question**. The task fills the ``{question}``
template variable from the inputs passed to ``crew.kickoff(inputs=...)``.

Callers reach the crew over MCP/HTTP and key their payload however they like
(``question``, ``topic``, ``query``, a bare string, ...). CrewAI would crash
interpolation if the exact key were missing (``Missing required template
variable 'question'``), or leave ``{question}`` literal when inputs are empty
-- so ``AssistantCrew`` normalizes every payload down to a non-empty
``question`` at the kickoff seam. Accept more inputs by extending
``QUESTION_KEYS`` / ``_coerce_question``.
"""

import json
import os

from crewai import Agent, Crew, Task

# Which model to use. The API key for it (e.g. OPENAI_API_KEY) must be in
# the environment at *run* time -- add it with `llnate keys`.
MODEL = os.environ.get("LLNATE_MODEL", "gpt-4o-mini")

# Caller keys we treat as "the question", in priority order. Clients over
# MCP/HTTP send arbitrary shapes; we map whatever they sent onto the
# `{question}` template variable so interpolation can never crash.
QUESTION_KEYS = ("question", "query", "topic", "prompt", "input", "text")

# Used when the caller sends nothing at all, so an empty kickoff never leaves
# `{question}` unfilled.
DEFAULT_QUESTION = "Introduce yourself and explain what you can help with."


def _coerce_question(inputs=None) -> dict:
    """Return an inputs dict that always carries a non-empty ``question``."""
    if not inputs:
        return {"question": DEFAULT_QUESTION}
    if not isinstance(inputs, dict):
        # A bare string / scalar payload.
        return {"question": str(inputs)}
    # A known alias with a non-empty value wins.
    for key in QUESTION_KEYS:
        value = inputs.get(key)
        if value:
            return {**inputs, "question": str(value)}
    # A single-value payload keyed under something unexpected.
    if len(inputs) == 1:
        (only_value,) = inputs.values()
        if only_value:
            return {**inputs, "question": str(only_value)}
    # Last resort: hand the whole payload to the model rather than drop it.
    return {**inputs, "question": json.dumps(inputs)}


class AssistantCrew(Crew):
    """A Crew that normalizes caller input to ``question`` before running.

    The base-image wrapper only ever calls ``.kickoff()``, so subclassing to
    coerce inputs is safe and invisible to it.
    """

    def kickoff(self, inputs=None, input_files=None, from_checkpoint=None):
        return super().kickoff(
            inputs=_coerce_question(inputs),
            input_files=input_files,
            from_checkpoint=from_checkpoint,
        )


assistant = Agent(
    role="Helpful Assistant",
    goal="Answer the user's question clearly and concisely.",
    backstory="A pragmatic generalist who gives short, correct answers.",
    llm=MODEL,
)

answer_question = Task(
    description="Answer the following question: {question}",
    expected_output="A clear, concise answer to the question.",
    agent=assistant,
)

crew = AssistantCrew(agents=[assistant], tasks=[answer_question])
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

# Local pointer to this project's LLAgent CR name (see `llnate login`).
# Not project source -- deliberately excluded from the repo.
.llnate.toml

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
# CLAUDE.md

Read [AGENTS.md](./AGENTS.md). It is the source of truth for this project:
the runtime contract your `crew.py` must satisfy, the input convention, and
how to build, verify, and ship the crew with `llnate`.
'''

# Written verbatim -- contains `{var}` template syntax and `${{ }}`-style
# examples, so it must never be passed through str.format.
AGENTS_MD = '''\
# AGENTS.md

Guidance for coding agents (and humans) writing crews in this repo. This is a
**CrewAI agent deployed on the Learning Layer cloud** (layernetes). The whole
project is essentially one file -- `crew.py` -- layered on top of the
`llagent-base` Docker image, which serves it over HTTP + MCP.

Read this before editing `crew.py`. The rules below are the ones we learned the
hard way; ignoring them means the failure only shows up at deploy time, which is
a slow, opaque loop.

---

## 1. The runtime contract (what the base image expects)

`llagent-base` bundles Python 3.12, a pinned CrewAI, and a FastAPI/FastMCP
wrapper (`server.py`). Your `Dockerfile` just does `FROM llagent-base:dev` +
`COPY . /app`.

**The one hard rule:** `crew.py` must expose a **module-level object named
`crew`** with a `.kickoff(inputs=...)` method. The wrapper does, in a threadpool:

```python
result = crew.kickoff(inputs=inputs)   # inputs is whatever the caller sent
return str(result)                     # <-- str() of the return value is served verbatim
```

Surfaces exposed (port 8000, plain HTTP):

| Endpoint | Behavior |
| --- | --- |
| `GET /healthz` | `200 {"ok": true}` only if the server is up **and** `crew.py` imported. `503` with the traceback if import failed. |
| `POST /kickoff` | `{"inputs": {...}}` -> `crew.kickoff(inputs=...)` -> `{"result": "<str(result)>"}` |
| `/mcp` | FastMCP (streamable HTTP), exposes one `kickoff(inputs: dict)` tool with the same behavior |
| `/docs`, `/openapi.json` | FastAPI surface |

Two consequences that bite:

- **`import crew` must never fail, even without credentials.** A broken import
  -> `/healthz` 503 -> the pod never goes Ready. Do **not** call a model API,
  read a required secret, or do anything that can throw at import time. Read
  config with `os.environ.get(...)` and defer all model calls to `kickoff`.
- **Whatever you return is `str()`-ified and served as-is.** For a CrewAI
  `Crew`, `str(CrewOutput)` is the final task's `.raw`. So the way to control
  the served text is to control the final task's raw output (see §4).

---

## 2. Pinned versions live in the base image, NOT in `pyproject.toml`

The base image pins its dependencies at build time:

```
crewai 1.15.1 · fastmcp 3.4.2 · fastapi 0.139.0 · uvicorn 0.49.0
```

Your `Dockerfile` only `COPY`s code -- **there is no `pip install` step**. So:

- **`pyproject.toml` dependencies are NOT installed into the runtime image.**
  Adding a library there does nothing at deploy time. If a crew needs an extra
  package, it has to be added to the base image (or a `RUN pip install` layer
  in your `Dockerfile`) -- not just `pyproject.toml`.
- **Don't pin `crewai` in `pyproject.toml` to "match" the runtime.** It can't
  change the runtime and creates a false impression. The base image is the
  source of truth for the version.
- When testing locally, install the **exact** pinned version (`crewai==1.15.1`)
  so behavior matches the cloud. See §6.

---

## 3. Input handling -- the `{question}` trap (this is what bit us)

CrewAI task descriptions use `{var}` template variables filled from
`kickoff(inputs=...)`. The gotcha in the interpolation logic:

- Empty inputs -> interpolation is **skipped** (`if not inputs: return`), so any
  `{var}` is left **literally** in the description (the model sees `{question}`).
- Non-empty inputs **missing that key** -> hard crash:
  `ValueError: Missing required template variable 'question'`.

Callers over MCP/HTTP send **arbitrary shapes** -- an LLM client might send
`{"topic": ...}`, `{"input": ...}`, `{"query": ...}`, etc. If your task uses
`{question}` and the caller didn't use exactly that key, the whole kickoff dies
before the crew even runs.

**Rule: never trust the caller to key inputs correctly. Normalize at the kickoff
seam.** The starter `crew.py` **already does this** -- `AssistantCrew` subclasses
`Crew` and runs `_coerce_question` before delegating, so an off-key or empty
payload can never crash interpolation:

```python
class AssistantCrew(Crew):
    def kickoff(self, inputs=None, input_files=None, from_checkpoint=None):
        return super().kickoff(
            inputs=_coerce_question(inputs),   # guarantees a non-empty 'question'
            input_files=input_files,
            from_checkpoint=from_checkpoint,
        )
```

`_coerce_question` maps a known caller key (`QUESTION_KEYS`: `question`, `query`,
`topic`, ...) -> a single-value payload -> a JSON dump of the whole payload,
falling back to `DEFAULT_QUESTION` when the caller sends nothing -- so `question`
is **always** present and non-empty. Subclassing is safe: the wrapper only calls
`.kickoff()` and nothing introspects the crew's type. When you add more template
vars, extend `QUESTION_KEYS` / `_coerce_question` to cover them the same way.

---

## 4. Deterministic output transforms -- use a Task guardrail, not the LLM

If the crew must produce output in a specific mechanical form (Pig Latin,
uppercase, strict JSON, redaction, a fixed template), **do not ask the LLM to do
it** -- LLMs are unreliable at character-level / format-exact work. Do it in code
via a **Task guardrail**, which CrewAI runs on the task output and which can
*replace* it.

Guardrail contract in crewai 1.15.1 (verified against the source):

- The callable takes **exactly one positional parameter** (the `TaskOutput`).
  An optional return annotation must be `tuple[bool, Any | str | TaskOutput]`.
- Returning `(True, <str>)` sets `task_output.raw = <str>` -- which is exactly
  what gets served. Read the model's text defensively:
  `getattr(output, "raw", None)` (fall back to `str(output)`).
- **Always return `(True, ...)`.** A `(False, err)` triggers a retry loop
  (`guardrail_max_retries`, default 3) and then raises. If your transform can
  handle any input (most can), never fail it.

```python
def pig_latin_guardrail(output) -> tuple[bool, str]:
    text = getattr(output, "raw", None) or str(output)
    return (True, to_pig_latin(text))   # to_pig_latin is a pure, unit-tested fn

answer_question = Task(..., guardrail=pig_latin_guardrail)
```

Keep the actual transform a **pure function** so you can unit-test it exhaustively
offline (case, punctuation, whitespace, multi-line, markdown) with no model call.

---

## 5. Credentials & config

- Model choice: `MODEL = os.environ.get("LLNATE_MODEL", "gpt-4o-mini")`.
- API keys (e.g. `OPENAI_API_KEY`) are read from the **environment at run time**.
  In the cloud, `entrypoint.sh` runs `sops exec-env keys.env ...` to decrypt
  `keys.env` into the process env (plaintext never hits disk). Locally, export
  them in your shell. Add/update them with `llnate keys`.
- Because keys are runtime-only, **import must stay credential-free** (see §1).

---

## 6. Verify locally before `llnate push` -- deploy is NOT your test loop

`crewai` isn't in the default environment, and a guardrail/interpolation mismatch
only surfaces at runtime. De-risk everything that doesn't need a model call by
building a scratch venv on the **exact pinned version**:

```sh
python3 -m venv .venv && .venv/bin/pip install crewai==1.15.1
```

With no API key you can still verify the parts that actually carry deploy risk:

1. **`crew.py` imports and constructs** -- the `Task`/`Crew`/guardrail field
   validators run at construction, so a bad guardrail signature fails here.
2. **The guardrail path** -- build a `TaskOutput(raw=...)`, call
   `crewai.utilities.guardrail.process_guardrail(output, fn, retry_count=0)`,
   and assert `str(output)` is the transformed text.
3. **Input normalization** -- call your `kickoff` normalizer on `{"topic": ...}`,
   `{"input": ...}`, `{}`, multi-key payloads, and assert the task description
   interpolates with no leftover `{var}` and no `ValueError`.
4. **The pure transform** -- unit-test edge cases directly.

Only the actual `crew.kickoff()` end-to-end run needs a real API key. Everything
above is offline. (These checks live as throwaway scripts; keep them if you want
regression coverage.)

---

## 7. Deploy workflow

```sh
llnate login    # provision cloud repo + age key (first time)
llnate keys     # encrypt model API keys into a committable keys.env
llnate push     # build on llagent-base, deploy, print public MCP + HTTP URLs
```

`llnate push` streams build/deploy progress. If `/healthz` is 503 after deploy,
the crew failed to import -- read the traceback it returns (see §1).

---

## 8. The `llnate` CLI

You already ran `llnate init` to create this project. The rest of the developer
loop:

| Command | What it does |
| --- | --- |
| `llnate plugin install` | Write coding-assistant hooks (`CLAUDE.md`) so your assistant can build the crew with you. |
| `llnate login` | Provision your cloud repo + age keypair and wire up the `layernetes` git remote (first time only). |
| `llnate keys [KEY=VALUE ...]` | Encrypt model API keys into a committable, sops/age-encrypted `keys.env`. Prompts interactively if no pairs are given. |
| `llnate push` | Push your committed `HEAD` to the cloud repo, build on `llagent-base`, deploy, and print the public MCP + HTTP URLs. Blocks until live (or failed). |
| `llnate status` | Print the current deploy phase and, once live, the agent's URLs. |
| `llnate delete` | Tear down the agent: deployment, namespace, and cloud repo (`--yes` / `-y` skips the prompt). |
| `llnate --version` | Print the CLI version. |

Typical first deploy, once `crew.py` is ready and committed:
`llnate login` -> `llnate keys OPENAI_API_KEY=sk-...` -> `llnate push`. After
that, commit your changes and `llnate push` again to ship each new revision.

---

## Checklist for a new crew

- [ ] `crew` is defined at module level and import has no side effects / no creds.
- [ ] Any `{var}` in a task description is normalized at the `kickoff` seam so
      arbitrary caller input can't crash interpolation (§3).
- [ ] Mechanical output format is enforced by a **guardrail returning
      `(True, str)`**, backed by a pure, unit-tested function -- not the LLM (§4).
- [ ] New runtime dependencies are added to the **base image**, not just
      `pyproject.toml` (§2).
- [ ] Verified offline against `crewai==1.15.1`: import, guardrail path, input
      normalization, pure transform (§6).
'''


def project_files(name: str) -> dict[str, str]:
    """Relative path -> content for a new agent project."""
    return {
        "crew.py": CREW_PY.replace("@@NAME@@", name),
        "pyproject.toml": PYPROJECT_TOML.format(name=name),
        "Dockerfile": DOCKERFILE,
        ".gitea/workflows/deploy.yaml": DEPLOY_WORKFLOW,
        "keys.env.example": KEYS_ENV_EXAMPLE,
        ".gitignore": GITIGNORE,
        "README.md": PROJECT_README.format(name=name),
        "AGENTS.md": AGENTS_MD,
        "CLAUDE.md": CLAUDE_MD,
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
