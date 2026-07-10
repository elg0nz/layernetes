# Layernetes setup — instructions for AI coding assistants

You are an AI coding assistant. Your user asked you to set up `llnate`, the
Layernetes CLI, so they can ship AI agents to the Learning Layer cloud. Follow
these steps in order. Canonical copy of this file:
https://layernetes.wtp.io/setup (also served at https://agents.wtp.io/setup).

**What you are setting up:** Layernetes turns a local CrewAI-powered agent
into a live public URL with one command. `llnate push` deploys it to a
sandboxed environment at `https://<sha>.agents.wtp.io`, callable over MCP and
plain HTTP. Background: https://layernetes.wtp.io/llms.txt

## 0. Check access first

Layernetes is members-only (Learning Layer AI floor). Accounts are
admin-provisioned — there is no self-serve signup. Ask the user if they have
Layernetes credentials. If not, tell them the access path and stop:

1. Become a member at https://frontiertower.io and join the AI floor.
2. Email business@sanscourier.ai for access.

## 1. Install llnate (and sops)

Requires Python 3.12+. Prefer an isolated tool install:

```sh
pipx install llnate        # or: uv tool install llnate
```

Fallback if neither pipx nor uv is available:

```sh
python3 -m pip install --user llnate
```

Or from source:

```sh
pip install "llnate @ git+https://github.com/elg0nz/layernetes#subdirectory=llnate"
```

Verify with `llnate --help`. It should list: `init`, `plugin`, `login`,
`keys`, `push`, `delete`.

`llnate keys` (step 7) also needs the `sops` binary on PATH — install it now
(`brew install sops` on macOS, or the user's package manager; see
https://github.com/getsops/sops).

## 2. Point the CLI at the cloud

`llnate` defaults to the production control plane
(`https://api.layernetes.learninglayer.ai`). If that name doesn't resolve
from the user's network, use the public alias instead — persist it in their
shell profile:

```sh
export LLNATE_API_URL=https://api.wtp.io
```

(For local/self-hosted clusters, point `LLNATE_API_URL` at that cluster's
`ll-api` instead — see https://github.com/elg0nz/layernetes#developing-locally.)

## 3. Scaffold the agent project

```sh
llnate init my-agent
cd my-agent
```

This creates a CrewAI agent project plus the Dockerfile and CI workflow the
cloud expects, and an `AGENTS.md` that documents the runtime contract and the
developer loop **for you** — read it before writing code.

## 4. Wire yourself into the project

```sh
llnate plugin install
```

This installs the AI coding hooks (CrewAI's "Build with AI" setup) so you can
build the agent with the user.

## 5. Build the agent

The project convention: expose a CrewAI `crew` object in `crew.py`. The
platform's base image imports it and mounts it behind FastMCP and FastAPI —
do **not** write your own HTTP or MCP server, and do not change the port
(8000) or the `/healthz`, `/mcp`, `/docs` routes.

## 6. Sign in — hand the terminal to the user

Run this **from inside the agent project directory** (it provisions a cloud
repo named after the current directory and configures a `layernetes` git
remote):

```sh
llnate login
```

This is a terminal username/password prompt, not a browser flow: it sends
the user's admin-provisioned Layernetes credentials to the control plane,
which mints an API token and provisions their cloud repo and age encryption
key. Let the user type the password themselves (the prompt hides input).
Never ask them to paste a password into chat. For non-interactive runs the
CLI also reads `LLNATE_USERNAME` / `LLNATE_PASSWORD` env vars — only suggest
those if the user sets them outside your view.

## 7. Encrypt secrets — this also triggers the first deploy

```sh
llnate keys
```

This prompts for `KEY=VALUE` pairs (e.g. `OPENAI_API_KEY=...`), encrypts
them with the user's age public key into a `keys.env` file that is safe to
commit — it is ciphertext — then **commits `keys.env` and `.sops.yaml` and
immediately runs a deploy** (`llnate push`). So run it when the agent is
ready to ship, and expect it to end by printing the live URLs. Rules for you:

- Let the user enter the values at the interactive prompt. Never write
  plaintext secrets into any file (including `.env`), never echo a secret
  back into the conversation, and avoid putting secrets in shell arguments
  (they land in shell history).
- The running agent is the only thing that can decrypt `keys.env` (in memory,
  at startup, via `sops exec-env`).

## 8. Ship revisions

After the first deploy, each subsequent:

```sh
llnate push
```

streams build and deploy progress, blocks until the agent is live, then
prints its public MCP and HTTP URLs. Verify:

```sh
curl https://<sha>.agents.wtp.io/healthz
```

Note: only the latest revision runs. Each push replaces the previous one and
the old `<sha>` hostname stops resolving.

## 9. Connect it to an MCP client (optional)

```sh
claude mcp add --transport http my-agent https://<sha>.agents.wtp.io/mcp
```

Any MCP client works; the same address also serves `POST /kickoff` and
interactive docs at `/docs`.

---

- Quickstart for agents: https://layernetes.wtp.io/llms.txt
- Deep reference (contracts, API shapes): https://layernetes.wtp.io/llms-full.txt
- Source: https://github.com/elg0nz/layernetes
- Built by https://sanscourier.ai for https://www.learninglayer.ai/
