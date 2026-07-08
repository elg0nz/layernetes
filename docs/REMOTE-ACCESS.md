---
title: Reaching a local kiac cluster from another machine (Tailscale)
description: Use a Tailscale subnet router to reach a local kiac cluster's ingress from another machine.
---

The local platform lives on the Mac that runs kiac: the ingress LoadBalancer
sits at `192.168.64.200`, and every platform hostname
(`api.192.168.64.200.sslip.io`, `gitea.…`, `*.agents.…`) resolves there via
[sslip.io](https://sslip.io). But `192.168.64.200` is an **Apple-container
vmnet address on `bridge101`** — it only exists on the host Mac. Another
computer can't reach it directly, even on the same LAN.

The fix is a **Tailscale subnet router**: the kiac host advertises its
`192.168.64.0/24` subnet into your tailnet, and other tailnet machines route
to it. Nothing about `llnate` changes — the sslip.io hostnames keep working
verbatim, including the per-`<sha>` agent URLs.

```
 other computer                     kiac host (Mac, "mhc")
 ──────────────                     ──────────────────────
 llnate / curl  ──▶ tailnet ──▶ 192.168.64.0/24 route ──▶ bridge101 ──▶ ingress
   (accept-routes)                 (advertise-routes,          (192.168.64.200)
                                    SNAT to 192.168.64.1)
```

## One-time setup

### 1. On the kiac host (the subnet router)

```sh
# Advertise the vmnet subnet. (macOS already has IP forwarding on; if not:
#   sudo sysctl -w net.inet.ip.forwarding=1)
tailscale set --advertise-routes=192.168.64.0/24
```

Then **approve the route** — advertised routes are inert until an admin
enables them:

1. Open <https://login.tailscale.com/admin/machines>.
2. Find this host (e.g. `mhc`); it shows a **Subnets** badge with
   `192.168.64.0/24` pending.
3. **⋯ → Edit route settings → check `192.168.64.0/24` → Save.**

Confirm it went active:

```sh
tailscale status --json | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["Self"]["AllowedIPs"])'
# → list now includes '192.168.64.0/24'
```

Tailscale SNATs subnet traffic to the router's `192.168.64.1`, so the kiac
nodes need no route back.

### 2. On the other computer (the client)

```sh
tailscale set --accept-routes
# macOS App Store build: no CLI flag — toggle Settings → "Use Tailscale subnets"
```

Verify reachability:

```sh
curl -s -w '\n%{http_code}\n' http://api.192.168.64.200.sslip.io/healthz
# → {"ok":true}  200
```

## Then: run llnate from the other computer

`llnate` needs no special config — only reachability (above) and a few
binaries. **No `kubectl` required**; the whole developer loop goes through
`ll-api` over HTTP and git over the tunnel.

```sh
# prereqs: git (push), sops + age (`llnate keys` shells out to sops)
brew install git sops age                     # Linux: your package manager

git clone <your-repo-url> layernetes && cd layernetes/llnate
python3.12 -m venv .venv && .venv/bin/pip install -e .
export PATH="$PWD/.venv/bin:$PATH"

# point at the cluster's control plane + local-dev creds
export LLNATE_API_URL=http://api.192.168.64.200.sslip.io
export LLNATE_USERNAME=layernetes-admin LLNATE_PASSWORD=layernetes-local-dev
#   (or one of the pre-provisioned dev1..dev5 accounts)

cd /tmp
llnate init test-agent && cd test-agent
llnate login                                  # sets git remote + fetches age key
llnate keys OPENAI_API_KEY=sk-...
git add keys.env .sops.yaml && git commit -m keys
llnate push                                   # prints the live URLs
```

Because the entire `192.168.64.0/24` subnet is routed, the URLs `push`
prints — `http://<sha>.agents.192.168.64.200.sslip.io` (`/healthz`, `/mcp`,
`/docs`) — are reachable from this machine too, so you can exercise the full
runtime contract remotely.

## Calling the deployed crew (HTTP and MCP)

Your `crew.py` is wrapped as a `kickoff` operation, served two ways from the
agent URL. `inputs` is whatever your crew's `kickoff(inputs=…)` expects.

```sh
URL=http://<sha>.agents.192.168.64.200.sslip.io   # the URL `push` printed

# --- HTTP (FastAPI): one request, JSON in/out ---
curl -s -X POST $URL/kickoff \
  -H 'Content-Type: application/json' \
  -d '{"inputs": {"topic": "quantum computing"}}'
# → {"result": "..."}         (browse $URL/docs for the live schema)

# --- MCP (FastMCP): add $URL/mcp to any MCP client (e.g. Claude), or by hand ---
SID=$(curl -sD - -o /dev/null -X POST $URL/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"cli","version":"0"}}}' \
  | awk 'tolower($1)=="mcp-session-id:"{print $2}' | tr -d '\r')

curl -s -o /dev/null -X POST $URL/mcp -H "mcp-session-id: $SID" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

curl -s -X POST $URL/mcp -H "mcp-session-id: $SID" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"kickoff","arguments":{"inputs":{"topic":"quantum computing"}}}}'
# → streams back `data: {...}` with the crew result (tool name: kickoff)
```

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `curl` to `api.…` hangs or returns empty | Route not active. On the host, `AllowedIPs` must include `192.168.64.0/24` (advertise **and** approve). |
| Host advertises but client can't reach | Client didn't accept: `tailscale set --accept-routes`, or GUI toggle on App Store builds. `tailscale status \| grep <host>` should show it offering the subnet. |
| `/healthz` returns 200 for *any* host | `/healthz` is the ingress-nginx controller's own path — not a real reachability test for a specific agent. Use `/docs`. |
| `llnate keys` errors | `sops` not on PATH — `brew install sops age`. |

To stop routing later: `tailscale set --advertise-routes=` on the host.
