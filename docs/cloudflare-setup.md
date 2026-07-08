---
title: Cloudflare edge setup
description: One-time Cloudflare setup for the Layernetes edge — the docs/blog Pages site and the shared Cloudflare Tunnel that fronts the cluster. CLI/API-first, no dashboard clicking.
---

The Cloudflare account holds two independent pieces of the Layernetes edge. They
share nothing but the account, and you can set them up in either order:

| Piece | What it is | How it's deployed |
| --- | --- | --- |
| **Pages site** | The docs + blog (`site/`, Astro Starlight) | GitHub Actions → `wrangler pages deploy` ([`.github/workflows/site.yml`](../.github/workflows/site.yml)) |
| **Shared tunnel** | The Cloudflare Tunnel that routes public platform + agent hostnames to the in-cluster ingress | `cloudflared` Deployment in the cluster (`ll-infra`) + one-time setup below |

The in-cluster workloads (Gitea, `ll-api`, the operator, `cloudflared` itself)
are Helm — see `ll-infra`. This document is only the account-side, one-time
setup that Helm can't do for you.

> **Why no Terraform/OpenTofu?** The whole edge is one Pages project, one
> tunnel, and a couple of wildcard DNS records — all set once and changed
> ~never. `wrangler` already owns the Pages deploy. IaC's carrying cost (state,
> drift, provider upgrades, importing existing resources) doesn't pay for
> itself at this size. If the footprint grows — more zones, Access policies,
> multiple environments — revisit then.

---

## Prerequisites (once per operator)

```sh
npm i -g wrangler   # or prefix every wrangler call with npx
wrangler login

# Get your Account ID (also shown by `wrangler login`'s output):
wrangler whoami
export CLOUDFLARE_ACCOUNT_ID=<account id from whoami>
```

Create a scoped API token for the raw API calls in Parts 2–3 — this is the one
step that needs the dashboard, since it's the credential every other call
authenticates with:

**My Profile → API Tokens → Create Token → Custom token**, scoped to:

| Scope | Permission |
| --- | --- |
| Account · Cloudflare Tunnel | Edit |
| Account · Cloudflare Pages | Edit *(only if not reusing the repo-secret token from Part 1)* |
| Zone · DNS | Edit, scoped to `learninglayer.ai` |
| Zone · Zone | Read, scoped to `learninglayer.ai` |
| Account · Access: Apps and Policies | Edit *(only needed for Part 4)* |

```sh
export CLOUDFLARE_API_TOKEN=<the token>

# Zone ID for learninglayer.ai, resolved via API (no dashboard click needed):
export ZONE_ID=$(curl -s "https://api.cloudflare.com/client/v4/zones?name=learninglayer.ai" \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result[0].id')
```

---

## Part 1 — The docs/blog site (Cloudflare Pages)

The site builds and deploys itself from CI on every push to `main` that touches
`site/**`. You do the one-time project + credentials setup below; CI does the
rest.

### 1. Create the Pages project

```sh
cd site
npm ci && npm run build
npx wrangler pages project create layernetes --production-branch=main
npx wrangler pages deploy dist --project-name=layernetes --branch=main
```

`wrangler pages deploy` will create the project on its own if it doesn't exist
yet, so the explicit `project create` above is just for a clean, inspectable
first step. Name it **`layernetes`** — it must match `--project-name=layernetes`
in the workflow.

The production URL is `https://layernetes.pages.dev` until you attach a custom
domain (below).

### 2. Add the two repo secrets

`.github/workflows/site.yml` deploys with `cloudflare/wrangler-action`, which
needs two repo secrets. Set them with the GitHub CLI instead of the
Settings UI:

```sh
gh secret set CLOUDFLARE_API_TOKEN --repo elg0nz/layernetes
gh secret set CLOUDFLARE_ACCOUNT_ID --repo elg0nz/layernetes
```

`gh secret set` without `--body` prompts for the value (or reads stdin) —
never pass a secret as a bare CLI argument, since it lands in shell history.

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | An API token with the **Cloudflare Pages → Edit** permission — mint it the same way as the Prerequisites token above, scoped to Pages:Edit (`My Profile → API Tokens → Create Token → *Edit Cloudflare Workers*` template also works, since it includes Pages). |
| `CLOUDFLARE_ACCOUNT_ID` | `$CLOUDFLARE_ACCOUNT_ID` from the Prerequisites section. |

### 3. (Optional) Custom domain

Once DNS is on Cloudflare (Part 3), attach a hostname via the API — Pages
custom domains have no dedicated `wrangler` subcommand:

```sh
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/layernetes/domains" \
  --request POST \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{"name": "layernetes.learninglayer.ai"}'
```

Then update `site: 'https://layernetes.pages.dev'` in `site/astro.config.mjs`
to the real URL so canonical links and the sitemap are correct.

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

This section is grounded in what `ll-infra`'s code actually does — read that
first, then do only as much on the Cloudflare side as the code requires.

### What the chart requires (verified from the code, not from Cloudflare's docs)

- [`ll-infra/templates/cloudflared/deployment.yaml`](../ll-infra/templates/cloudflared/deployment.yaml)
  runs `cloudflared` with args `tunnel --no-autoupdate --metrics 0.0.0.0:2000
  run` and exactly one env var, `TUNNEL_TOKEN`, sourced from a Secret key
  named `token`. There is no config file, no volume mount — nothing else. That
  means whatever tunnel you create **must be remotely-managed** (ingress rules
  configured on Cloudflare's side): this Deployment has no way to load a local
  `config.yml`.
- The Secret defaults to the name **`ll-cloudflared-token`**
  ([`templates/cloudflared/secret.yaml`](../ll-infra/templates/cloudflared/secret.yaml)
  creates it from `cloudflared.token` in values, if set). Production instead
  points `cloudflared.existingSecret: ll-cloudflared-token`
  ([`argocd/application.yaml`](../ll-infra/argocd/application.yaml)), whose
  header comment says this Secret "must exist out-of-band before the first
  sync" — i.e. production expects you to have already created it by hand.
- `cloudflared.enabled` defaults to `true`
  ([`values.yaml`](../ll-infra/values.yaml)) but is explicitly `false` in
  [`values-local.yaml`](../ll-infra/values-local.yaml) ("nothing sits in front
  of the ingress controller locally") — none of this Part applies to local
  dev; use the port-forward flow in the repository README instead.
- The hostnames that need to reach the cluster come straight from
  `global.hosts` in `values.yaml`:

  | `global.hosts` key | Value | Notes |
  | --- | --- | --- |
  | `gitea` | `gitea.layernetes.learninglayer.ai` | fixed hostname |
  | `api` | `api.layernetes.learninglayer.ai` | fixed hostname |
  | `agents` | `agents.layernetes.learninglayer.ai` | ll-operator builds `<sha>.agents.layernetes.learninglayer.ai` per agent revision — see repo README |

- All three route to the same origin inside the cluster. The repo's own docs
  ([`README.md`](../README.md), [`docs/QA.md`](./QA.md)) confirm the ingress
  controller's Service is `ingress-nginx-controller` in the `ingress-nginx`
  namespace — `http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80`
  from inside the cluster.

### What's genuinely outside this repo

Creating the tunnel, routing its ingress, and producing a connector token is
Cloudflare account state — none of it lives in `ll-infra`, so there's no chart
code to verify it against. Do it once, however you're comfortable: the
Cloudflare dashboard (**Networking → Tunnels → Create a tunnel**, then add a
Public Hostname route for each hostname above pointing at the ingress-nginx
origin) is the first-party, always-correct path. Whichever method you use,
only two constraints actually come from the code above:

1. It must be a **remotely-managed** tunnel (dashboard-created tunnels are
   remotely-managed by default) — never a locally-managed one, since this
   Deployment can't load a config file.
2. Whatever token comes out of it goes into the Secret named above, under key
   `token`.

If you'd rather script it than click through the dashboard, the equivalent
Cloudflare API calls are:

```sh
# Create the tunnel (config_src: cloudflare = remotely-managed):
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel" \
  --request POST \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{"name": "layernetes-shared", "config_src": "cloudflare"}'
# → save result.id as $TUNNEL_ID

# Get the connector token:
export TUNNEL_TOKEN=$(curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/token" \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result')

# Route each hostname from the table above at the ingress controller
# (the http_status:404 entry is a required catch-all — cloudflared rejects
# an ingress config that doesn't end with one):
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/configurations" \
  --request PUT \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{
    "config": {
      "ingress": [
        { "hostname": "gitea.layernetes.learninglayer.ai", "service": "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80" },
        { "hostname": "api.layernetes.learninglayer.ai", "service": "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80" },
        { "hostname": "*.agents.layernetes.learninglayer.ai", "service": "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80" },
        { "service": "http_status:404" }
      ]
    }
  }'
```

### Create the Secret ll-infra expects

Whichever way you got the token, hand it to the cluster with the exact command
from the repo README's "Install (GitOps, production)" section:

```sh
kubectl -n layernetes create secret generic ll-cloudflared-token \
  --from-literal=token=<cloudflare tunnel token>
```

For values-file-managed installs, set `cloudflared.token` directly instead and
let `secret.yaml` create it — sops-encrypt that values file, never commit the
token in plaintext.

---

## Part 3 — DNS

Each hostname from Part 2's `global.hosts` table needs a **proxied**
(orange-cloud) `CNAME` pointing at the tunnel, created via the DNS records API:

```sh
for name in "gitea.layernetes" "api.layernetes" "*.agents.layernetes"; do
  curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
    --request POST \
    --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    --json "{\"type\": \"CNAME\", \"name\": \"$name\", \"content\": \"$TUNNEL_ID.cfargotunnel.com\", \"proxied\": true}"
done
```

| Type | Name | Target | Proxy |
| --- | --- | --- | --- |
| CNAME | `gitea.layernetes` | `<TUNNEL_ID>.cfargotunnel.com` | Proxied |
| CNAME | `api.layernetes` | `<TUNNEL_ID>.cfargotunnel.com` | Proxied |
| CNAME | `*.agents.layernetes` | `<TUNNEL_ID>.cfargotunnel.com` | Proxied |

- `$TUNNEL_ID` is the tunnel's UUID from Part 2. The record target is always
  `<TUNNEL_ID>.cfargotunnel.com`.
- **Proxied is required** — that's what routes the hostname into the tunnel.
  A DNS-only (grey-cloud) record won't reach the connector.
- Unlike the dashboard (which offers to create the matching CNAME for you when
  you add a Public Hostname), the API path never does this automatically —
  the loop above is the whole step, not an optional extra.

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
`ONBOARDING.md` currently documents the dashboard flow for the Access app
itself; the `access/apps` and `access/policies` API endpoints used above for
Tunnel/DNS work the same way for Access if you want that step scripted too —
ask for it as a follow-up if so.

---

## Checklist

- [ ] Pages project `layernetes` created (`wrangler pages project create` + first deploy)
- [ ] Repo secrets `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` set (`gh secret set`)
- [ ] (opt) Custom domain attached via the Pages domains API; `site:` updated in `site/astro.config.mjs`
- [ ] Remotely-managed tunnel created; ingress routes `gitea.`, `api.`, and `*.agents.layernetes.learninglayer.ai` to `ingress-nginx-controller.ingress-nginx.svc.cluster.local:80`, ending in `http_status:404`
- [ ] Connector token in the `ll-cloudflared-token` Secret (`ll-infra`'s expected name/key)
- [ ] Proxied CNAMEs for `gitea.`, `api.`, `*.agents.layernetes` → `<TUNNEL_ID>.cfargotunnel.com`
- [ ] (opt) Access app gating `gitea.…/user/sign_up` — see `docs/ONBOARDING.md`
