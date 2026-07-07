# ll-tofu

[OpenTofu](https://opentofu.org/) module for the **Cloudflare edge** of
Layernetes — the account-side resources that sit in front of the cluster. The
in-cluster workloads stay in Helm (`ll-infra`); this module owns the Cloudflare
control plane.

## What it manages

| File | Resources |
| --- | --- |
| `tunnel.tf` | The shared Cloudflare Tunnel (`config_src = "cloudflare"`, i.e. remotely-managed), its ingress config (`*.agents.<domain>` and `*.<domain>` → the in-cluster ingress controller), the proxied CNAMEs, and the connector **token** (as an output). |
| `access.tf` | *Optional.* A Cloudflare Access app gating the Gitea signup page behind GitHub identity (see the Onboarding guide). Enabled only when `github_identity_provider_id` is set. |
| `pages.tf` | *Optional, off by default.* The docs/blog Pages project + custom domain. The site CI (`.github/workflows/site.yml`) owns the project via `wrangler pages deploy`; enable `manage_pages` only if you move ownership fully here. |

The in-cluster `cloudflared` Deployment + secret stay in `ll-infra`.

## The tunnel token seam

This module creates the tunnel and exposes its connector token as a sensitive
output (`tunnel_token`). That value has to reach the in-cluster secret the
`ll-infra` `cloudflared` Deployment reads — `Secret ll-cloudflared-token`, key
`token`. It is **not** wired automatically; feed it in via sops or a manual
step:

```sh
tofu output -raw tunnel_token   # → put into ll-cloudflared-token / token
```

## Usage

```sh
cd ll-tofu
cp terraform.tfvars.example terraform.tfvars   # fill in account_id, zone_id
export CLOUDFLARE_API_TOKEN=…                   # token with Tunnel + DNS (+ Access/Pages) edit

tofu init
tofu plan
tofu apply
```

> **Already have a dashboard-managed tunnel?** Do **not** `apply` blind — that
> creates a *duplicate* tunnel and rotates the token. Import the existing one
> first:
> ```sh
> tofu import cloudflare_zero_trust_tunnel_cloudflared.shared <account_id>/<tunnel_id>
> ```
> then reconcile `tofu plan` before applying.

## State backend

Defaults to **local state** (`terraform.tfstate` in this directory, gitignored).
Fine for solo/experimental use. To move to remote state on **Cloudflare R2**
(S3-compatible) for a team:

1. Create an R2 bucket (e.g. `ll-tofu-state`) and an R2 **S3 API token**
   (Access Key ID + Secret Access Key).
2. Uncomment the `backend "s3"` block in `versions.tf` and set `bucket` +
   the R2 `endpoints.s3` URL (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`).
3. Export the R2 token as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
4. `tofu init -migrate-state`.

## Provider

`cloudflare/cloudflare` **v5** (validated against v5.21.1). Note v5 was a large
breaking change from v4 — resource names and attribute shapes here follow v5
(e.g. `cloudflare_dns_record`, attribute-style tunnel `config = { ingress = […] }`).
The committed `.terraform.lock.hcl` pins provider versions.
