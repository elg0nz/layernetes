# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Layernetes is a platform for building, shipping, and hosting CrewAI-powered AI
agents on a Kubernetes cloud (Talos Linux in production). A developer writes an
agent locally and `llnate push` deploys it to a sandboxed, per-namespace pod
with a public URL callable over MCP or HTTP.

Read `README.md` first — it is the source of truth for the architecture, the
end-to-end flow, and the frozen contracts. This file covers what the README
doesn't: commands and the non-obvious mechanics of working in the tree.

## Monorepo layout

Five independent packages plus a docs site and an infra module. There is no
top-level build; each package is built/tested on its own.

| Path | Stack | Role |
| --- | --- | --- |
| `llnate/` | Python + Typer | Developer CLI (`init`, `plugin install`, `login`, `keys`, `push`, `delete`) |
| `ll-api/` | Python + FastAPI | Control-plane API (login, Gitea provisioning, age keys, deploy status) |
| `ll-operator/` | Python + kopf | K8s operator reconciling `LLAgent` CRs into namespaces/deployments/ingresses |
| `llagent-base/` | Docker | Base image for every agent: FastMCP/FastAPI wrapper + sops/age entrypoint |
| `ll-infra/` | Helm | Platform chart: Gitea, `ll-api`, `ll-operator`, `cloudflared` |
| `ll-tofu/` | OpenTofu | Cloudflare edge (tunnel, Access, Pages) — the account-side, out-of-cluster resources |
| `site/` | Astro Starlight | Docs + blog, deployed to Cloudflare Pages |
| `hack/` | Bash | Local-dev (mostly kiac) provisioning scripts |

## Commands

### Python packages (`llnate`, `ll-api`, `ll-operator`)

Each has its own `pyproject.toml` and `tests/`. Work from inside the package dir:

```sh
cd ll-api        # or llnate / ll-operator
pip install -e '.[dev]'
pytest -q                          # all tests for this package
pytest -q tests/test_api.py        # one file
pytest -q tests/test_api.py::test_name   # one test
```

`llagent-base` has **no** `pyproject.toml` — it is a thin wrapper baked into the
base image. CI installs its test deps by hand and the pins must match
`llagent-base/Dockerfile`:

```sh
cd llagent-base && pip install pytest fastmcp==3.4.2 fastapi==0.139.0 && pytest -q
```

CI (`.github/workflows/ci.yml`) runs exactly the above per package as a matrix.

### Helm chart (`ll-infra`)

```sh
helm repo add gitea https://dl.gitea.com/charts/   # once
helm dependency build ll-infra
helm lint ll-infra -f ll-infra/values-local.yaml
helm template layernetes ./ll-infra -n layernetes -f ll-infra/values-local.yaml   # render
```

**Bare defaults MUST fail to render** — the chart ships no credentials and
guards against rendering without them. CI asserts this. Always pass
`-f ll-infra/values-local.yaml` (add `-f ll-infra/values-kiac.yaml` for kiac).

### Site (`site/`)

```sh
cd site && npm ci && npm run build   # npm run dev for local preview
```

### OpenTofu edge (`ll-tofu/`)

```sh
cd ll-tofu && tofu init && tofu plan   # needs terraform.tfvars + CLOUDFLARE_API_TOKEN
```

## Architecture notes that aren't obvious from a single file

- **The four contracts in README.md ("Contracts" section) are the seams
  between packages and are frozen for the MVP:** the `LLAgent` custom resource,
  the `ll-api` REST API, the agent runtime contract (port 8000, `/healthz`,
  `/mcp`, `/docs`, a `crew` object in `crew.py`), and the CI→`ll-api` build
  callback. Changing any of them means changing multiple packages **and** the
  README's Contracts section in the same PR.

- **Deploy model is SHA-addressed and last-write-wins.** Each revision's
  hostname includes the short SHA (`<sha>.agents.<domain>`). A new `spec.sha`
  replaces the Deployment + Ingress; old `<sha>` hostnames stop resolving. Only
  the latest revision runs (no history/rollback in the MVP). `llnate push`
  polls `GET /v1/agents/{name}/status` every 2s and waits until the reported
  `sha` matches the one it pushed — so a stale Failed/Ready status from the
  prior revision can't end the poll early.

- **`ll-operator/operator/` deliberately has no `__init__.py`.** A top-level
  package named `operator` would shadow Python's stdlib `operator` module. The
  operator is run by file path (`kopf run .../operator/main.py`), not installed;
  `main.py` inserts its own dir on `sys.path` and imports its siblings
  (`builders`, `k8s`) flat. `pyproject.toml` installs only dependencies
  (`packages = []`). Keep this pattern; don't "fix" it into a normal package.

- **Secrets never hit disk in plaintext.** Credentials are sops/age-encrypted
  into a committed `keys.env`; the age private key lives as a K8s Secret; the
  agent entrypoint runs `sops exec-env` at startup so plaintext exists only in
  process memory. See README "Managing credentials".

- **`ll-api` login is password-based in the MVP**, not real OAuth — it mints a
  Gitea personal access token and that token *is* the bearer for every user
  endpoint (identity resolved per-request via Gitea's API). The endpoint shape
  matches the eventual OAuth flow so downstream code won't change. See the
  module docstring in `ll-api/app/main.py`.

## Local development = the acceptance test

The whole platform runs on any local cluster (kiac preferred on Apple silicon;
Colima/k3s/kind also work). The end-to-end smoke test **is** running the real
user flow against a local `ll-api`:

```sh
export LLNATE_API_URL=http://api.127.0.0.1.sslip.io:8080
llnate init hello-agent && cd hello-agent
llnate login && llnate keys && llnate push
curl http://<sha>.agents.127.0.0.1.sslip.io:8080/healthz
```

Full setup, the kiac-specific `hack/` scripts, and troubleshooting (registry
trust, the vmnet TSO/GSO offload bug, port-forwards) are in README "Developing
locally". Hostnames use `sslip.io` so no `/etc/hosts` edits are needed.

## Working conventions

- Confirm the current branch before coding; use it by default (don't create or
  switch branches unless asked). Commit/push only when asked; keep diffs tied to
  the request and match local style.
- Python everywhere is intentional — the CLI and `ll-api` share pydantic
  models. Prefer reusing shared schemas over re-declaring shapes.
- The `.github/workflows/site.yml` deploy is path-filtered to `site/**` and only
  deploys on push to `main`; PRs build-only.
