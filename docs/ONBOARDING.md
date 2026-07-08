---
title: Onboarding (production / Talos)
description: How a new user signs up and ships their first agent on the production cluster.
---

**Decision: self-serve registration, gated by GitHub identity at the edge.**
Gitea registration is open, but the signup page sits behind a Cloudflare
Access policy that requires logging in with GitHub. Everything else — git
traffic, the `llnate` CLI, deployed agents — stays open, because those
surfaces already carry their own auth (Gitea credentials / bearer tokens)
or are meant to be public (agents).

A new user's entire onboarding:

1. Visit `https://gitea.layernetes.learninglayer.ai/user/sign_up` → Cloudflare
   interposes "sign in with GitHub" → allowed users reach the Gitea signup
   form and pick a username + password.
2. `pipx install llnate` (or clone + install), then
   `llnate init my-agent && cd my-agent && llnate login` — the PAT, age
   keypair, cloud repo, and CI wiring all provision lazily on that first
   login. Nothing else to hand out.

## Why gate only `/user/sign_up`

Cloudflare Access applications are host + path scoped. Gating the whole
`gitea.` host would break non-browser traffic (`git push` from laptops,
`llnate`'s API calls) unless every client did the `cloudflared access`
dance. But Gitea self-registration is *only* reachable via the web form
(the REST path, `POST /api/v1/admin/users`, is admin-only), so protecting
`/user/sign_up` is sufficient to control who can ever get an account —
and it's the only URL a newcomer touches before they have credentials.

| Surface | Edge policy | Auth story |
| --- | --- | --- |
| `gitea.…/user/sign_up` | Cloudflare Access: GitHub login required | the gate |
| `gitea.…` (everything else) | open | Gitea session / PAT / basic auth |
| `api.…` (ll-api) | open | bearer token (Gitea PAT); login needs an existing account |
| `*.agents.…` | open | public by design (MCP + HTTP for anyone) |

## Cloudflare setup (one-time, dashboard or Terraform)

1. **Zero Trust → Settings → Authentication → Login methods**: add
   **GitHub** as an identity provider (a GitHub OAuth app; Cloudflare
   docs walk through it).
2. **Zero Trust → Access → Applications → Add an application** (self-hosted):
   - Application domain: `gitea.layernetes.learninglayer.ai`, path `user/sign_up`.
   - Session duration: short (e.g. 30 minutes) — it only guards signup.
3. **Policy** (Allow): Login method = GitHub, plus whichever membership
   rule fits — specific emails, email domain, or GitHub organization
   membership (org rules require the GitHub IdP to be org-authorized).
4. Nothing else changes: the existing tunnel already routes the wildcard
   hostnames to the in-cluster ingress.

## Chart configuration

Production values (see the `gitea.gitea.config.service` block in
`ll-infra/values.yaml`):

```yaml
gitea:
  gitea:
    config:
      service:
        DISABLE_REGISTRATION: false      # tier-2: open, Access gates the page
        ENABLE_CAPTCHA: false            # Access is the bot filter
        DEFAULT_KEEP_EMAIL_PRIVATE: true
```

Local development keeps `DISABLE_REGISTRATION: true` (there is no Access
locally); pre-create accounts instead:

```sh
GITEA_URL=http://gitea.<LB-IP>.sslip.io GITEA_ADMIN=layernetes-admin \
GITEA_ADMIN_PASSWORD=... hack/provision-users.sh alice bob
```

## Trade-offs and the upgrade path

- Anyone who passes the GitHub gate chooses an arbitrary Gitea username;
  there is no enforced link between the GitHub identity and the Gitea
  account. Acceptable now; revisit if squatting/abuse appears.
- Users still manage a Gitea password. The planned tier-3 upgrade —
  `llnate login` doing a real OAuth authorization-code flow against
  Gitea, with Gitea federating to GitHub — removes passwords entirely
  and needs no changes to keys, CI tokens, or the operator. The login
  endpoint shapes were kept OAuth-compatible for exactly this.
