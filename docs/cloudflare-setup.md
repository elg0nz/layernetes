---
title: Cloudflare edge setup
description: One-time Cloudflare setup for the Layernetes edge — the docs/blog Pages site and the shared Cloudflare Tunnel that fronts the cluster.
---

The Cloudflare account holds two independent pieces of the Layernetes edge. They
share nothing but the account, and you can set them up in either order:

| Piece | What it is | How it's deployed |
| --- | --- | --- |
| **Pages site** | The docs + blog (`site/`, Astro Starlight) | GitHub Actions → `wrangler pages deploy` ([`.github/workflows/site.yml`](../.github/workflows/site.yml)) |
| **Shared tunnel** | The Cloudflare Tunnel that routes public platform + agent hostnames to the in-cluster ingress | `cloudflared` Deployment in the cluster (`ll-infra`) + one-time dashboard setup below |

The in-cluster workloads (Gitea, `ll-api`, the operator, `cloudflared` itself)
are Helm — see `ll-infra`. This document is only the account-side, click-once
setup that Helm can't do for you.

> **Why no Terraform/OpenTofu?** The whole edge is one Pages project, one
> tunnel, and a couple of wildcard DNS records — all set once and changed
> ~never. `wrangler` already owns the Pages deploy. IaC's carrying cost (state,
> drift, provider upgrades, importing existing resources) doesn't pay for
> itself at this size. If the footprint grows — more zones, Access policies,
> multiple environments — revisit then.

---

## Part 1 — The docs/blog site (Cloudflare Pages)

The site builds and deploys itself from CI on every push to `main` that touches
`site/**`. You do the one-time project + credentials setup; CI does the rest.

### 1. Create the Pages project

Direct Upload (no Git integration — CI pushes the built `dist/`):

- **Dashboard:** Workers & Pages → Create → Pages → **Upload assets**. Name it
  **`layernetes`** (must match `--project-name=layernetes` in the workflow).
  You can upload an empty/placeholder build to create it; CI overwrites it on
  the next push to `main`.
- **Or CLI**, once, from `site/`:
  ```sh
  npm ci && npm run build
  npx wrangler pages deploy dist --project-name=layernetes --branch=main
  ```
  The first `wrangler pages deploy` creates the project if it doesn't exist.

The production URL is `https://layernetes.pages.dev` until you attach a custom
domain (below).

### 2. Add the two repo secrets

`.github/workflows/site.yml` deploys with `cloudflare/wrangler-action`, which
needs:

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | An API token with the **Cloudflare Pages → Edit** permission. My Profile → API Tokens → Create Token → *Edit Cloudflare Workers* template, or a custom token scoped to Pages:Edit. |
| `CLOUDFLARE_ACCOUNT_ID` | Your account ID (Workers & Pages overview, right sidebar). |

Add both under the repo's **Settings → Secrets and variables → Actions**.

### 3. (Optional) Custom domain

Once DNS is on Cloudflare (Part 3), attach a hostname in **Pages → your project
→ Custom domains** (e.g. `layernetes.learninglayer.ai`). Then update
`site: 'https://layernetes.pages.dev'` in `site/astro.config.mjs` to the real
URL so canonical links and the sitemap are correct.

### How CI behaves

- **Pull request** touching `site/**` → builds only (a compile check). No deploy.
- **Push to `main`** touching `site/**` → builds, then deploys to production.
  The workflow passes `--branch=main` explicitly: Actions checks out a detached
  HEAD, and without it wrangler's branch auto-detection can land the build on a
  preview URL instead of production.

Until the two secrets and the project exist, the deploy step just fails on
push to `main` (the build step still runs and passes on PRs) — nothing else
breaks.

---

## Part 2 — The shared Cloudflare Tunnel

Public traffic reaches the cluster through **one** remotely-managed tunnel. The
connector is the in-cluster `cloudflared` Deployment (from `ll-infra`); it runs
with a token and pulls its ingress rules from Cloudflare. You create the tunnel
and its routing in the dashboard, then hand the token to the cluster.

### 1. Create a remotely-managed tunnel

**Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared.** Name it
e.g. **`layernetes-shared`**. "Remotely-managed" means the ingress config lives
on Cloudflare's side (next step), not in a local `cloudflared` config file.

Cloudflare shows a connector **token** on the install screen. Copy it — that's
the value the cluster needs.

### 2. Feed the token into the cluster

The `ll-infra` `cloudflared` Deployment reads the token from a Kubernetes
Secret. Either set it in Helm values or create the Secret directly:

```sh
# Option A — Helm values (ll-infra/values.yaml):
#   cloudflared:
#     token: "<the connector token>"        # chart creates the Secret
#   or point existingSecret at a Secret you manage (sops-encrypted).

# Option B — create the Secret by hand:
kubectl create secret generic ll-cloudflared-token \
  --namespace <platform-ns> \
  --from-literal=token='<the connector token>'
```

Prefer sops/`existingSecret` over a plaintext token in `values.yaml` for
anything but throwaway local use.

### 3. Route public hostnames to the in-cluster ingress

In the tunnel's **Public Hostname** tab, add a rule per public hostname, all
pointing at the ingress controller. The ingress then routes by `Host` header,
so a couple of **wildcards** cover everything:

| Public hostname | Service (origin) |
| --- | --- |
| `*.agents.layernetes.learninglayer.ai` | `http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80` |
| `*.layernetes.learninglayer.ai` | `http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80` |

- The first wildcard carries the per-`<sha>` **agent** URLs
  (`<sha>.agents.…`). The second carries the single-label **platform**
  hostnames (`gitea.`, `api.`, …). Both keep in sync with
  `global.hosts` in [`ll-infra/values.yaml`](../ll-infra/values.yaml).
- The origin is a cluster-internal DNS name; the connector resolves it from
  inside the cluster, so it never leaves Cloudflare's network unencrypted.
- Remotely-managed tunnels append the mandatory `http_status:404` catch-all
  automatically — you don't add it by hand in the dashboard.

---

## Part 3 — DNS

Each public hostname needs a **proxied** (orange-cloud) `CNAME` pointing at the
tunnel. In the zone for `learninglayer.ai` (**DNS → Records**):

| Type | Name | Target | Proxy |
| --- | --- | --- | --- |
| CNAME | `*.agents.layernetes` | `<TUNNEL_ID>.cfargotunnel.com` | Proxied |
| CNAME | `*.layernetes` | `<TUNNEL_ID>.cfargotunnel.com` | Proxied |

- `<TUNNEL_ID>` is the tunnel's UUID (Zero Trust → Networks → Tunnels → your
  tunnel; also in the connector install command). The record target is always
  `<TUNNEL_ID>.cfargotunnel.com`.
- **Proxied is required** — that's what routes the hostname into the tunnel.
  A DNS-only (grey-cloud) record won't reach the connector.
- When you add a Public Hostname to a remotely-managed tunnel in the dashboard,
  Cloudflare usually offers to create the matching CNAME for you; if it does,
  you can skip adding it manually here.

---

## Part 4 — Signup gate (Cloudflare Access, optional)

Production onboarding gates only the Gitea **signup page** behind GitHub login,
using a Cloudflare Access application on
`gitea.layernetes.learninglayer.ai` at path `user/sign_up`. Everything else
stays open (it carries its own auth or is public by design).

That setup — the rationale, the exact Access policy, and the matching
`DISABLE_REGISTRATION` chart value — is documented in full in
[`docs/ONBOARDING.md`](./ONBOARDING.md). Follow it after the tunnel and DNS are
live, since Access sits in front of the same hostnames the tunnel serves.

---

## Checklist

- [ ] Pages project `layernetes` created (Direct Upload)
- [ ] Repo secrets `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` set
- [ ] (opt) Custom domain attached; `site:` updated in `site/astro.config.mjs`
- [ ] Tunnel `layernetes-shared` created; token in `ll-cloudflared-token`
- [ ] Public Hostname rules for both wildcards → in-cluster ingress
- [ ] Proxied wildcard CNAMEs → `<TUNNEL_ID>.cfargotunnel.com`
- [ ] (opt) Access app gating `gitea.…/user/sign_up` — see `docs/ONBOARDING.md`
