# Layernetes

Build, ship, and host [CrewAI](https://github.com/crewAIInc/crewAI)-powered AI agents on the [Learning Layer](https://www.learninglayer.ai/) cloud — a Kubernetes platform running on Talos Linux.

Layernetes is developed by [Sanscourier.ai](https://sanscourier.ai), which licenses it to [Learning Layer](https://www.learninglayer.ai/) for the Learning Layer cloud. Sanscourier.ai reserves all rights — see [License](#license).

Write your agent locally with your favorite coding assistant, then `llnate push` deploys it to a sandboxed environment with its own public URL, callable via MCP or plain HTTP.

## Quickstart

```sh
# 1. Scaffold a new LLAgent: a CrewAI-based agent project, plus the
#    Dockerfile and CI workflow it needs in our cloud — and an AGENTS.md that
#    documents the runtime contract and the llnate developer loop for your
#    coding assistant
llnate init my-agent
cd my-agent

# 2. Install the AI coding hooks so Claude (or your favorite
#    coding agent) can build your LLAgent with you.
#    This wires up CrewAI's "Build with AI" setup for you:
#    https://github.com/crewAIInc/crewAI#build-with-ai
llnate plugin install

# 3. Build your agent with your coding assistant — the hooks
#    from step 2 give it everything it needs

# 4. Ship it to the Learning Layer cloud
llnate login   # OAuth handshake; provisions your cloud repo and keys
llnate keys    # encrypt your credentials (API keys, etc.)
llnate push    # deploy — streams build/deploy progress, prints your URLs
```

`llnate push` blocks until your agent is live, then prints its public URLs. Anyone can call it:

- **MCP** — every LLAgent ships with a built-in [FastMCP](https://github.com/jlowin/fastmcp) server, so it plugs directly into MCP clients like Claude.
- **HTTP API** — a plain [FastAPI](https://fastapi.tiangolo.com/) interface for everything else.

## Managing credentials: `llnate keys`

Your agent needs secrets (model API keys, service credentials) but they should never land in a repo in plaintext. Layernetes uses [sops](https://github.com/getsops/sops) with [age](https://github.com/FiloSottile/age) encryption:

1. When you `llnate login`, you receive an age public key, e.g. `age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p`.
2. `llnate keys` encrypts your credentials with that key into a `keys.env` file that is committed alongside your code.
3. The matching private key is stored as a Kubernetes Secret in the Learning Layer cloud, guarded by RBAC and encrypted at rest (Talos-native etcd encryption).
4. At deploy time, `ll-operator` mounts the age key and your still-encrypted `keys.env` into your agent's pod. The agent entrypoint (scaffolded by `llnate init`) decrypts them **in-memory** at startup via [`sops exec-env`](https://github.com/getsops/sops#passing-secrets-to-other-processes) — plaintext credentials never touch etcd, a rendered Secret, or disk.

Your credentials are readable by exactly one thing: your running agent — literally. (Vault is the planned upgrade path once we need audit logging and key rotation.)

## How it works

1. **Login.** `llnate login` completes an OAuth handshake with `ll-api`, our control-plane service. `ll-api` provisions your repo on the Gitea instance in the Learning Layer cloud, generates your age keypair (storing the private half as an RBAC-guarded Kubernetes Secret), and configures your local git remote.
2. **Push.** `llnate push` pushes your code to Gitea. A Gitea Actions pipeline (scaffolded by `llnate init`) builds your container image and pushes it to Gitea's built-in OCI registry.
3. **Deploy.** The pipeline reports the new image to `ll-api`, which updates your `LLAgent` custom resource. `ll-operator` reconciles it: creates your agent's namespace and deploys the container, mounting your age key and encrypted `keys.env`. The agent entrypoint decrypts them in-memory at startup (`sops exec-env`), so plaintext secrets never exist outside the running process.
4. **Expose.** `ll-operator` creates an Ingress for the agent with its `<sha>` hostname — the URL includes the SHA of the deployed code, so every revision has a stable, addressable URL. A shared [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`cloudflared` running in the cluster) forwards the wildcard `*.agents.` hostname to the in-cluster ingress controller, which routes by hostname from there.
5. **Report back.** `llnate push` streams build and deploy progress from `ll-api` and exits by printing your agent's MCP and HTTP URLs.
6. **Serve.** Clients reach the agent through that URL via MCP (FastMCP) or HTTP (FastAPI).

Every LLAgent runs as a container in its own Kubernetes namespace, giving two layers of isolation: namespaces (with restricted permissions and network policies) separate agents from each other, and the cluster nodes themselves run on [Cloud Hypervisor](https://www.cloudhypervisor.org/) VMs, separating agent workloads from the host.

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

## Contracts

These four interfaces are the seams between packages. They are frozen for the MVP — change them only with a PR that updates this section.

### The `LLAgent` custom resource

The contract between `ll-api` (writes it) and `ll-operator` (reconciles it):

```yaml
apiVersion: layernetes.learninglayer.ai/v1alpha1
kind: LLAgent
metadata:
  name: gonz-hello-agent          # <owner>-<agent>, unique cluster-wide
  namespace: layernetes           # CRs live in the platform namespace
spec:
  owner: gonz                     # Gitea username
  repo: gonz/hello-agent          # Gitea repo
  image: gitea.../gonz/hello-agent:3f2a91c
  sha: 3f2a91c                    # short SHA; becomes the hostname
  keySecretRef: age-key-gonz      # Secret holding the age private key
status:
  phase: Pending | Deploying | Ready | Failed
  url: https://3f2a91c.agents.layernetes.learninglayer.ai
  message: ""                     # human-readable detail on Failed
```

**Revision semantics (MVP):** only the latest revision runs. A new `spec.sha` replaces the agent's Deployment and Ingress; previous `<sha>` hostnames stop resolving. Revision history and rollback are post-MVP.

### `ll-api` REST API

Everything `llnate` and CI talk to. Auth: `Authorization: Bearer <token>` — user tokens issued at login, repo-scoped tokens injected into CI at provisioning time.

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `POST /v1/auth/login` | none | Start OAuth flow against Gitea (localhost-callback); returns user token |
| `GET /v1/me` | user | Identity + the user's age **public** key (used by `llnate keys`) |
| `POST /v1/agents` | user | Provision: create Gitea repo, generate age keypair, create `LLAgent` shell |
| `POST /v1/agents/{name}/builds` | CI | CI callback: `{"sha": "...", "image": "..."}` — updates `LLAgent.spec` |
| `GET /v1/agents/{name}/status` | user | `{"phase": "...", "url": "...", "message": "...", "sha": "..."}` — `llnate push` polls this every 2s. `sha` is the deployed revision (from `LLAgent.spec.sha`); `push` waits until it matches the sha it pushed, so a stale status from the previous revision can't end the poll early. |
| `DELETE /v1/agents/{name}` | user | Teardown: delete `LLAgent`, namespace, Gitea repo (backs `llnate delete`) |

### Agent runtime contract

What every LLAgent container must expose — the `llnate init` template and `llagent-base` image guarantee it, and `ll-operator` depends on it:

- **Port `8000`**, plain HTTP.
- **`GET /healthz`** — liveness/readiness; the operator gates `Ready` on it.
- **`/mcp`** — the FastMCP server.
- **`/docs` + REST routes** — the FastAPI surface.
- **User code convention:** the project exposes a CrewAI `crew` object in `crew.py`; the base image's entrypoint imports it and mounts it behind FastMCP and FastAPI.
- **Startup:** the entrypoint runs `sops exec-env keys.env` (age key mounted at `/var/run/secrets/llnate/age.key`) so decrypted credentials exist only in process memory.

### CI → `ll-api` callback

The Gitea Actions workflow (scaffolded by `llnate init`) builds the image, pushes it to the Gitea OCI registry, then reports:

```
POST /v1/agents/{name}/builds
Authorization: Bearer <repo-scoped token, injected as an Actions secret at provisioning>
{"sha": "3f2a91c", "image": "gitea.../gonz/hello-agent:3f2a91c"}
```

That call is the *only* coupling between CI and the platform — the pipeline knows nothing about Kubernetes.

## Repository layout

| Package | Stack | Description |
| --- | --- | --- |
| `llnate` | Python + [Typer](https://typer.tiangolo.com/) | CLI for the developer loop: `init`, `plugin install`, `login`, `keys`, `push` |
| `ll-api` | Python + FastAPI | Control-plane API: OAuth login, Gitea repo provisioning, age keypair issuance, deploy status |
| `ll-operator` | Python + [kopf](https://kopf.readthedocs.io/) | Kubernetes operator that reconciles `LLAgent` resources: namespaces, secrets, deployments, ingresses |
| `llagent-base` | Docker | Base image for all agents: Python, pinned CrewAI, the FastMCP/FastAPI wrapper, sops/age, entrypoint |
| `ll-infra` | Helm | Charts for the platform: Gitea (git + Actions + OCI registry), `ll-api`, `ll-operator`, `cloudflared` |

Python everywhere, on purpose: one language across CLI, control plane, and operator means shared models (the CLI and `ll-api` use the same pydantic schemas) and no context switching. Routing needs no custom edge code — the ingress controller routes `<sha>` hostnames, and the Cloudflare Tunnel just points at it.

The production cluster runs on [Talos Linux](https://www.talos.dev/), a minimal, API-managed OS built for Kubernetes.

## Developing locally

The entire platform — Gitea, `ll-api`, `ll-operator`, and deployed LLAgents — runs on any Kubernetes cluster, including a laptop or a Mac mini. This is the primary development environment (the Talos cluster is not always... plugged in). macOS with **kiac is the preferred setup**; Colima, k3s, and kind also work.

### What's different from production

Everything — the git-push-to-deploy pipeline, sops/age secrets, the operator — runs exactly as in production. Since `ll-operator` always exposes agents via Ingress, the only real difference is what sits in front of the ingress controller: a Cloudflare Tunnel in production, nothing locally.

| Concern | Production | Local |
| --- | --- | --- |
| Cluster | Talos Linux on Cloud Hypervisor VMs | kiac / Colima / k3s / kind |
| Reaching agents | Cloudflare Tunnel → in-cluster Ingress | same Ingress, reached directly ([sslip.io](https://sslip.io) hostnames) |
| Node isolation | Cloud Hypervisor VMs | kiac: per-node VMs; others: namespaces only |
| Git + CI + registry | Gitea (in-cluster) | same |
| Secrets | K8s Secret + `sops exec-env` | same |

### Prerequisites

```sh
brew install kubectl helm sops age git   # Linux: use your package manager
```

Plus a cluster — pick one:

**macOS, Apple silicon — [kiac](https://saiyam1814.github.io/kiac/) (preferred).** "Kubernetes in Apple Containers" boots each node in its own lightweight VM via Apple's Virtualization framework — the closest local analogue to our production Cloud-Hypervisor nodes. Requires Apple's [`container`](https://github.com/apple/container) 1.0 runtime (macOS 26+ for multi-node).

```sh
# after installing apple/container 1.0 from Apple's releases:
brew install saiyam1814/tap/kiac
kiac doctor
kiac create cluster --workers 2
kubectl get nodes                  # each node is its own VM
```

kiac ships MetalLB, local-path storage, and metrics-server, but no ingress controller — install ingress-nginx (command below). Three kiac-specific setup steps, all scripted in `hack/`:

```sh
# MetalLB ships with no address pool — give it one on the VM subnet, then
kubectl apply -f - <<'EOF'   # (or use your own range)
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata: {name: kiac-pool, namespace: metallb-system}
spec: {addresses: [192.168.64.200-192.168.64.220]}
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata: {name: kiac-l2, namespace: metallb-system}
spec: {ipAddressPools: [kiac-pool]}
EOF
hack/kiac-net-offload-fix.sh        # vmnet mangles TSO/GSO on forwarded pod traffic; rerun after node restarts
hack/kiac-registry-trust.sh gitea.<LB-IP>.sslip.io 10.96.100.100   # plain-HTTP registry trust + direct route
```

Install the platform with the kiac overlay layered on top of the local values (`-f ll-infra/values-local.yaml -f ll-infra/values-kiac.yaml`) — it moves hostnames to `*.<LB-IP>.sslip.io` and routes in-cluster registry traffic around the ingress. `hack/kiac-load.sh <image>` is the `kind load` equivalent for iterating on `ll-api`/`ll-operator`.

**macOS — Colima.**

```sh
brew install colima docker
colima start --kubernetes --cpu 4 --memory 8 --disk 60
kubectl config use-context colima
```

**Linux — k3s (or kind).**

```sh
curl -sfL https://get.k3s.io | sh -    # or: kind create cluster --name layernetes
```

For kiac and kind, install an ingress controller (Colima/k3s ship Traefik):

```sh
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
```

### 1. Install the platform

`ll-infra` ships a `values-local.yaml` that enables Gitea (with Actions and the OCI registry), deploys `ll-api` and `ll-operator`, disables `cloudflared`, and sets hostnames under `*.127.0.0.1.sslip.io` (resolves to localhost, no `/etc/hosts` edits).

```sh
helm dependency build ll-infra
helm install layernetes ./ll-infra -n layernetes --create-namespace \
  -f ll-infra/values-local.yaml
kubectl -n layernetes get pods -w   # wait for gitea, ll-api, ll-operator, runner
```

Get traffic to the ingress controller:

- **kiac:** no port-forward needed — MetalLB gives the ingress controller a real external IP (`kubectl -n ingress-nginx get svc`); set the chart hostnames to `*.<that-IP>.sslip.io` and use port 80 directly.
- **Everything else:** `kubectl -n kube-system port-forward svc/traefik 8080:80` (kind: forward `svc/ingress-nginx-controller` in `ingress-nginx` instead), then use `http://gitea.127.0.0.1.sslip.io:8080`, `http://api.127.0.0.1.sslip.io:8080`, `http://<sha>.agents.127.0.0.1.sslip.io:8080`.

### 2. Run the full loop

Point the CLI at your local control plane, then run the same flow a real user runs — this is the end-to-end smoke test and our acceptance test:

```sh
export LLNATE_API_URL=http://api.127.0.0.1.sslip.io:8080

llnate init hello-agent && cd hello-agent
llnate login    # OAuth against your local ll-api / Gitea
llnate keys     # encrypt a dummy OPENAI_API_KEY into keys.env
llnate push     # push → Actions build → operator deploy → prints URLs

curl http://<sha>.agents.127.0.0.1.sslip.io:8080/healthz
```

### Working on individual components

- **`ll-api` / `ll-operator`:** build the image, get it into the cluster, restart:

  ```sh
  docker build -t ll-api:dev ./ll-api
  # Colima: docker-built images are already visible to k3s
  # kind:   kind load docker-image ll-api:dev --name layernetes
  # kiac:   push to the in-cluster Gitea registry and reference that image
  kubectl -n layernetes set image deploy/ll-api ll-api=ll-api:dev
  ```

- **`llnate`:** pure client-side; run from source against your `LLNATE_API_URL`.
- **Helm charts:** `helm upgrade layernetes ./ll-infra -n layernetes -f ll-infra/values-local.yaml`.

### Troubleshooting

- **Builds can't push to / cluster can't pull from the Gitea registry.** The registry is plain HTTP locally; containerd must trust it as insecure. k3s reads `/etc/rancher/k3s/registries.yaml` — map `gitea.127.0.0.1.sslip.io:8080` to `http://gitea-http.layernetes.svc:3000`. On Colima, edit inside the VM (`colima ssh`) and `colima restart`; on kind, use `containerdConfigPatches`.
- **Actions runner idle / jobs queued.** The runner registers against Gitea at startup; if Gitea wasn't ready, `kubectl -n layernetes rollout restart deploy/gitea-act-runner`. Image builds need its docker-in-docker sidecar running too.
- **`sslip.io` doesn't resolve.** Some corporate DNS blocks wildcard DNS; fall back to `/etc/hosts` entries or `nip.io`.
- **Bulk transfers stall on kiac (image pulls/pushes hang after a few MB, small requests fine).** The Apple vmnet stack mishandles TSO/GSO super-frames on *forwarded* pod traffic — node-local TCP is unaffected, which makes it look like a registry or ingress bug. `hack/kiac-net-offload-fix.sh` disables NIC offloads on every node (measured: stalled → ~600 MB/s). Not persistent across VM restarts.
- **Out of resources (Colima).** `colima stop && colima start --kubernetes --cpu 6 --memory 12` — cluster state survives.
- **Port-forward drops.** It's not resilient; rerun it, or use the ingress service's NodePort with the VM IP for something longer-lived.

## License

Copyright © 2026 [Sanscourier.ai](https://sanscourier.ai). All rights
reserved.

Layernetes was developed by Sanscourier.ai, which licenses it to
[Learning Layer](https://www.learninglayer.ai/) for operating the Learning
Layer cloud, and releases the source to the public under the
[GNU Affero General Public License v3.0 or later](LICENSE)
(AGPL-3.0-or-later). Under the AGPL you may use, study, modify, and
redistribute Layernetes — but if you run a modified version as a network
service, you must offer its source to the users of that service under the
same license.

Sanscourier.ai retains all rights not expressly granted by the AGPL,
including the exclusive right to offer Layernetes under alternative
commercial terms. For commercial licensing, contact
<business@sanscourier.ai>. Contributions are accepted by application only —
see [CONTRIBUTING.md](CONTRIBUTING.md).

## References

- [CrewAI](https://github.com/crewAIInc/crewAI)
- [sops](https://github.com/getsops/sops) / [age](https://github.com/FiloSottile/age)
- [Talos Linux](https://www.talos.dev/)
- [Cloud Hypervisor](https://www.cloudhypervisor.org/)
- [FastMCP](https://github.com/jlowin/fastmcp) / [FastAPI](https://fastapi.tiangolo.com/)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
