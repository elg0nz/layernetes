variable "cloudflare_api_token" {
  description = "Cloudflare API token. Prefer the CLOUDFLARE_API_TOKEN env var; leave blank to use it."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID that owns the tunnel, Access apps, and Pages project."
  type        = string
}

variable "zone_id" {
  description = "Cloudflare zone ID for the DNS zone (e.g. the zone for learninglayer.ai)."
  type        = string
}

variable "platform_domain" {
  description = "Base hostname for the platform. Agent, Gitea, and API hostnames live under this."
  type        = string
  default     = "layernetes.learninglayer.ai"
}

variable "tunnel_name" {
  description = "Name for the shared Cloudflare Tunnel."
  type        = string
  default     = "layernetes-shared"
}

variable "origin_service" {
  description = "In-cluster origin the tunnel forwards public hostnames to (the ingress controller). The cloudflared connector resolves this from inside the cluster."
  type        = string
  default     = "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80"
}

# ── Access (optional): gate Gitea signup behind GitHub identity ──────────────
# Requires a GitHub login method configured in Zero Trust → Settings →
# Authentication. Supply its identity provider ID to enable the Access app;
# leave blank to skip Access entirely.
variable "github_identity_provider_id" {
  description = "Zero Trust GitHub identity provider ID. Blank disables the Gitea signup Access app."
  type        = string
  default     = ""
}

variable "github_organization" {
  description = "GitHub organization whose members may reach the Gitea signup page."
  type        = string
  default     = ""
}

# ── Pages (optional): manage the docs/blog site project in Tofu ──────────────
# The site's CI currently creates/owns the Pages project via `wrangler pages
# deploy` (Direct Upload). Do NOT also manage it here unless you move ownership
# fully to Tofu — double ownership causes conflicts. Off by default.
variable "manage_pages" {
  description = "If true, manage the Cloudflare Pages project + custom domain here instead of via wrangler."
  type        = bool
  default     = false
}

variable "pages_project_name" {
  description = "Cloudflare Pages project name (must match the CI --project-name)."
  type        = string
  default     = "layernetes"
}

variable "site_hostname" {
  description = "Custom domain for the docs/blog site (only used when manage_pages = true)."
  type        = string
  default     = ""
}
