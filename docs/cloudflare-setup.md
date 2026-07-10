---
title: Cloudflare edge setup
description: Where the Layernetes edge (Pages site + Cloudflare Tunnel) is provisioned, and the contract this repo's code depends on.
---

The Cloudflare account behind Layernetes belongs to SansCourier, and is
provisioned as code in the private **`sanscourier-infra`** repo (Terraform,
not included here — `layernetes` is open source). This document only records
the resulting **end state**: the hostnames that exist, and the contract this
repo's own code (`ll-infra`) depends on to serve them.

## Domain layout (`wtp.io`)

| Hostname | Serves | Provisioned by |
| --- | --- | --- |
| `wtp.io` (apex) | SansCourier's Vercel app — unrelated to Layernetes | `sanscourier-infra` (unchanged) |
| `layernetes.wtp.io` | The docs/blog site (`site/`, Astro Starlight) | Cloudflare Pages custom domain, `sanscourier-infra` |
| `agents.wtp.io` (apex) | Same Pages project as `layernetes.wtp.io` — exists so `agents.wtp.io/setup` serves the agent-setup instructions (see below) | Cloudflare Pages custom domain, `sanscourier-infra` |
| `gitea.wtp.io` | Gitea | Cloudflare Tunnel, `sanscourier-infra` |
| `api.wtp.io` | `ll-api` | Cloudflare Tunnel, `sanscourier-infra` |
| `*.agents.wtp.io` | Per-`<sha>` agent pods | Cloudflare Tunnel, `sanscourier-infra` |

Note the wildcard `*.agents.wtp.io` does **not** cover the `agents.wtp.io`
apex — the apex is attached to the `layernetes` Pages project as an
additional custom domain. The site's landing page tells coding agents to
`fetch agents.wtp.io/setup`; a Pages rewrite (`site/public/_redirects`,
`/setup → /AGENTS-SETUP.md 200`) makes that path serve
[`site/public/AGENTS-SETUP.md`](../site/public/AGENTS-SETUP.md) on both
hostnames. Canonical URLs on every page point at `layernetes.wtp.io`, so the
duplicate host doesn't split search indexing.

The Pages site deploys independently via `wrangler pages deploy` (see
`site/README.md`) — nothing in `ll-infra` depends on it. The other three
hostnames route through one shared, remotely-managed Cloudflare Tunnel to the
cluster's ingress controller; the tunnel, its ingress rules, and their DNS
records all live in `sanscourier-infra`, not here.

## The contract `ll-infra` depends on

The in-cluster `cloudflared` Deployment
([`ll-infra/templates/cloudflared/deployment.yaml`](../ll-infra/templates/cloudflared/deployment.yaml))
runs with no config file — just `tunnel --no-autoupdate --metrics
0.0.0.0:2000 run` and a single env var, `TUNNEL_TOKEN`, sourced from a Secret
key named `token`. That fixes two things any tunnel pointed at this cluster
must satisfy:

1. It must be **remotely-managed** (`config_src: cloudflare`) — this
   Deployment has no way to load a local `config.yml`.
2. Its connector token must land in a Secret named **`ll-cloudflared-token`**
   ([`templates/cloudflared/secret.yaml`](../ll-infra/templates/cloudflared/secret.yaml)
   creates it from `cloudflared.token` in values, or point
   `cloudflared.existingSecret` at one you manage out-of-band — production
   does the latter, see [`argocd/application.yaml`](../ll-infra/argocd/application.yaml)).

`sanscourier-infra` exposes the token as a Terraform output
(`wtp_tunnel_token`); getting it into the cluster is a manual hand-off, not
something either repo automates:

```sh
kubectl -n layernetes create secret generic ll-cloudflared-token \
  --from-literal=token="$(tofu -chdir=terraform output -raw wtp_tunnel_token)"
```

(Run from `sanscourier-infra`, with `op run --env-file=terraform/op.env --`
prefixed so the provider has credentials.)

`cloudflared.enabled` defaults to `true` ([`values.yaml`](../ll-infra/values.yaml))
but is `false` in [`values-local.yaml`](../ll-infra/values-local.yaml) — none
of this applies to local dev; use the port-forward flow in the repository
README instead.

## Gitea registration

Closed — `DISABLE_REGISTRATION: true` ([`values.yaml`](../ll-infra/values.yaml))
disables self-registration server-side, so `gitea.wtp.io/user/sign_up` isn't
reachable regardless of who hits it. No Cloudflare-side gate needed. Only the
admin creates accounts; see [`docs/ONBOARDING.md`](./ONBOARDING.md).

## Keeping the two repos in sync

If the domain or hostname layout changes, update it in both places:
`sanscourier-infra`'s `terraform/wtp.tf` (the actual DNS/Tunnel/Pages
resources) and this repo's `global.hosts` values
([`ll-infra/values.yaml`](../ll-infra/values.yaml)) plus `ll-operator`'s
`AGENTS_DOMAIN` — those are what `ll-infra`'s own Ingress/cloudflared config
render against, independent of what Cloudflare is told to route.
