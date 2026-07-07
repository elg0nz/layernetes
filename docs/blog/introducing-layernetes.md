# Introducing Layernetes: `git push` your AI agents

Building an AI agent has never been easier. Hosting one is still a mess.

You write a CrewAI crew in an afternoon — the model does most of the typing — and then you hit the part nobody demos: a Dockerfile, a registry, secrets that can't live in the repo, an ingress, a URL, TLS, CI that ties it all together. The agent took an afternoon. The plumbing takes a week, and you get to do it again for the next one.

**Layernetes collapses that week into one command.** You build your agent locally with your favorite coding assistant, then:

```sh
llnate push
```

`push` blocks until your agent is live and prints its public URLs — one for MCP, one for plain HTTP. Anyone (or any Claude) can call it. That's the whole pitch: write the agent, `push`, done.

This post is both the introduction and the usage guide. By the end you'll know what Layernetes is, how to ship an agent on it, and what happens under the hood when you do.

---

## The 30-second version

Five commands take you from empty directory to a live, publicly-addressable agent:

```sh
llnate init my-agent      # scaffold a CrewAI agent + everything the cloud needs
cd my-agent
llnate plugin install     # wire up AI coding hooks (CrewAI's "Build with AI")
# ... build your agent with your coding assistant ...
llnate login              # provisions your cloud repo + encryption keys
llnate keys               # encrypt your API keys into the repo, safely
llnate push               # deploy — streams progress, prints your URLs
```

Everything else in this post is an expansion of those six lines.

---

## Walking through it

### `llnate init` — scaffold

```sh
llnate init my-agent
cd my-agent
```

You get a real CrewAI project — a `crew.py` with a `crew` object you'll fill in — *plus* the things you'd otherwise hand-write: a `Dockerfile`, a CI workflow, a sops-aware entrypoint, and a `keys.env.example`. None of it is boilerplate you have to understand. It's the contract the cloud expects, pre-satisfied.

### `llnate plugin install` — build with AI

```sh
llnate plugin install
```

This installs coding hooks so your assistant (Claude, or whatever you use) has everything it needs to build the agent *with* you — CrewAI's "Build with AI" setup, wired up. Then you write your crew the way you write anything now: describe what you want, review the diff, iterate.

The only convention to remember: your project exposes a CrewAI `crew` object in `crew.py`. The base image imports it and mounts it behind both an MCP server and a REST API automatically. You write the agent; you don't write the server.

### `llnate keys` — secrets that never leak

Your agent needs credentials — model API keys, service tokens — and they must never sit in a repo in plaintext. This is the part most "deploy your agent" tools wave away, and it's where Layernetes is deliberately strict.

```sh
llnate keys OPENAI_API_KEY=sk-...
```

Here's the model, end to end:

1. When you `llnate login`, you're issued an **age public key** — something like `age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p`.
2. `llnate keys` encrypts your credentials with that key into a `keys.env` file — using [sops](https://github.com/getsops/sops) + [age](https://github.com/FiloSottile/age) — and you commit that encrypted file *alongside your code*. It's safe in git; it's ciphertext.
3. The matching **private** key lives only in the cloud, as a Kubernetes Secret guarded by RBAC and encrypted at rest.
4. At deploy time your agent's entrypoint runs `sops exec-env keys.env`, decrypting your credentials **in-memory at startup**. Plaintext never touches disk, never lands in a rendered Kubernetes Secret, never hits etcd.

The result is a property worth stating plainly: **your credentials are readable by exactly one thing — your running agent process.** Not the repo, not a Secret, not a shell into the pod. We verified this the boring way — `exec` into a running agent and the credential simply isn't in the environment; only the server process (PID 1, the `sops exec-env` child) has it in memory. The file on disk is still `ENC[AES256_GCM,...]`.

> One gotcha the guide part owes you: `llnate` never auto-commits your `keys.env`. After `llnate keys`, run `git add keys.env .sops.yaml && git commit` yourself. That's intentional — nothing touches your git history without you asking.

### `llnate login` — get your repo and keys

```sh
llnate login
```

One handshake with the control plane provisions everything: a git repo for your agent in the cloud, your age keypair (public half handed to you, private half sealed as an RBAC-guarded Secret), and your local git remote. Nothing to configure, no dashboard to click through.

### `llnate push` — ship

```sh
llnate push
```

This is the whole platform firing in sequence, and `push` narrates it live:

```
Pushing to layernetes remote...
Waiting for my-agent to deploy (polling every 2s)...
  phase: Pending
  phase: Deploying
  phase: Ready

Agent is live:
  HTTP: https://3f2a91c.agents.layernetes.learninglayer.ai
  MCP:  https://3f2a91c.agents.layernetes.learninglayer.ai/mcp
  Docs: https://3f2a91c.agents.layernetes.learninglayer.ai/docs
```

The first build takes a few minutes (the CI runner pulls the base image once, then caches). After that, redeploys are fast. And notice the hostname: it's the **SHA of your deployed code**. Every revision has its own stable, addressable URL.

---

## What just happened

Six lines of your time hid a full git-push-to-deploy pipeline. Here's the path your code took:

1. **Login.** `llnate login` talks to `ll-api`, the control-plane service. It creates your repo on the cloud's Gitea instance, generates your age keypair, and points your git remote at it.
2. **Push.** `llnate push` pushes to Gitea. A Gitea Actions pipeline — scaffolded into your repo by `init` — builds your container and pushes it to Gitea's built-in OCI registry.
3. **Deploy.** The pipeline reports the new image to `ll-api`, which writes it into your `LLAgent` custom resource. `ll-operator` (a Kubernetes operator) reconciles it: creates a dedicated namespace, deploys your container, and mounts your age key plus encrypted `keys.env`. Your entrypoint decrypts in-memory at startup.
4. **Expose.** The operator creates an Ingress at your `<sha>` hostname. A shared Cloudflare Tunnel forwards the wildcard `*.agents.` hostname to the in-cluster ingress controller, which routes by hostname from there.
5. **Serve.** Clients reach your agent over MCP or HTTP.

```
 developer                       Learning Layer cloud (K8s on Talos Linux)
 ─────────                       ──────────────────────────────────────────
 llnate ──login──▶ ll-api ─────▶ provisions Gitea repo + age keys
 llnate ──push───▶ Gitea ──▶ Gitea Actions ──build──▶ OCI registry
                                   │
                                ll-api ──▶ LLAgent CR ──▶ ll-operator
                                                              │
                          age key (K8s Secret) ──mounted──▶ LLAgent pod
                                                          (own namespace,
                                                           in-memory decrypt,
                                                           FastMCP + FastAPI)
                                                              │
 users ◀── https://<sha>.…  ◀── Cloudflare Tunnel ◀── Ingress ◀┘
```

Five small packages make this work, and they're deliberately boring:

| Package | What it is |
| --- | --- |
| `llnate` | The CLI you just used — the entire developer loop |
| `ll-api` | Control-plane API: login, repo provisioning, key issuance, deploy status |
| `ll-operator` | The Kubernetes operator that turns an `LLAgent` resource into a running agent |
| `llagent-base` | The base image every agent builds on: CrewAI, the MCP/HTTP wrapper, sops/age |
| `ll-infra` | Helm charts for the platform itself: Gitea, `ll-api`, `ll-operator`, `cloudflared` |

Python everywhere, on purpose. The CLI and the control plane share the same schemas; there's no glue language, no bespoke edge code. The ingress controller routes `<sha>` hostnames, and the tunnel just points at it.

---

## Calling your agent — HTTP *and* MCP

Once `push` prints a URL, your crew is live at `<sha>.agents.…` and callable **two ways from the same endpoint**. You wrote a `crew` object in `crew.py`; the base image wraps it as a `kickoff` operation and exposes it over both a REST API and an MCP server. Whatever the caller prefers, it's the same crew.

The surface:

| Path | What it is |
| --- | --- |
| `GET /healthz` | liveness — `{"ok":true,"agent":"…"}` (the operator gates `Ready` on it) |
| `POST /kickoff` | **REST**: `{"inputs":{…}}` → `{"result":"…"}` |
| `/mcp` | **MCP** ([FastMCP](https://github.com/jlowin/fastmcp)) exposing a `kickoff` tool |
| `/docs`, `/openapi.json` | [FastAPI](https://fastapi.tiangolo.com/) interactive docs + schema |

### Over HTTP

The plain path — one request, JSON in, JSON out:

```sh
URL=https://<sha>.agents.layernetes.learninglayer.ai   # the URL `push` printed

curl -s -X POST $URL/kickoff \
  -H 'Content-Type: application/json' \
  -d '{"inputs": {"topic": "quantum computing"}}'
# → {"result": "...your crew's output..."}
```

`inputs` is whatever your crew's `kickoff(inputs=…)` expects — pass `{}` if it takes none. Browse `/docs` for the live schema.

### Over MCP

Point any MCP client — Claude included — at `<url>/mcp` and your agent shows up as a tool named `kickoff`. No SDK, no wrapper: it's a real [streamable-HTTP MCP](https://modelcontextprotocol.io) server that happens to be your crew.

To drive it by hand, it's the standard MCP handshake. `initialize` returns an `mcp-session-id` header you echo back on every later call:

```sh
# 1. initialize — grab the session id from the response headers
SID=$(curl -sD - -o /dev/null -X POST $URL/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"cli","version":"0"}}}' \
  | awk 'tolower($1)=="mcp-session-id:"{print $2}' | tr -d '\r')

# 2. say hello
curl -s -o /dev/null -X POST $URL/mcp -H "mcp-session-id: $SID" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3. call the crew (responses stream back as `data:` SSE lines)
curl -s -X POST $URL/mcp -H "mcp-session-id: $SID" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"kickoff","arguments":{"inputs":{"topic":"quantum computing"}}}}'
```

`tools/list` (same session) returns the `kickoff` tool and its schema — exactly what an MCP client reads to know how to call your agent. It's not a shim; it's a real MCP server, and it's the *same* crew the REST endpoint runs.

---

## Revisions and teardown

**Revisions are latest-only, by design (for now).** Push a new commit and its `<sha>` hostname goes live; the previous revision's Deployment and Ingress are replaced, and the old hostname stops resolving. One agent, one live URL, addressed by content. (Revision history and rollback are on the roadmap, not the MVP.)

Done with an agent?

```sh
llnate delete
```

That removes the deployment, its namespace, and the cloud repo. Clean exit, no orphans.

---

## Run the whole thing on your laptop

Here's the part that makes it hackable: **the entire platform runs on a laptop.** Gitea, the control plane, the operator, your deployed agents — the same git-push-to-deploy pipeline, the same sops/age secrets, the same operator. Not a mock. The same code.

The only difference between local and production is what sits in front of the ingress: a Cloudflare Tunnel in the cloud, nothing locally (you reach agents directly via [sslip.io](https://sslip.io) hostnames). On Apple silicon the preferred setup is [kiac](https://saiyam1814.github.io/kiac/) — "Kubernetes in Apple Containers" — which boots each node in its own lightweight VM, the closest local analogue to the production nodes. Colima, k3s, and kind work too.

```sh
brew install kubectl helm sops age git
# then bring up a cluster (kiac on Apple silicon), install the chart, and
# llnate points at your local control plane — same five commands.
```

Everything in this post — `init → login → keys → push`, the in-memory secret decrypt, the SHA-addressed URLs, teardown — has been run end-to-end on exactly this local setup.

---

## Where it's going

The MVP is intentionally small, and the seams are drawn so the upgrades don't move them:

- **Onboarding** moves to self-serve, gated by GitHub identity at the edge — sign up once, `llnate login`, and you're building.
- **Login** becomes a full OAuth flow (the endpoint shapes were kept OAuth-compatible from day one), so there are no passwords to manage.
- **Secrets** graduate to Vault when we need audit logging and key rotation — the `sops exec-env` boundary stays put.
- **Revisions** gain history and rollback.

The production cluster runs on [Talos Linux](https://www.talos.dev/) — a minimal, API-managed OS built for Kubernetes — with each agent doubly isolated: its own namespace, on nodes that are themselves VMs.

---

## Try it

The pitch, one more time: you already know how to build the agent. Layernetes is the part after that — the registry, the secrets, the ingress, the URL — reduced to `llnate push`. Write the crew, push it, hand someone the URL.

That's the whole idea.
