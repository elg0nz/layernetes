# Optional: manage the docs/blog Pages project here. Off by default because the
# site CI (.github/workflows/site.yml) creates and owns the project via
# `wrangler pages deploy`. Enable only if you move ownership fully to Tofu.
resource "cloudflare_pages_project" "site" {
  count = var.manage_pages ? 1 : 0

  account_id        = var.cloudflare_account_id
  name              = var.pages_project_name
  production_branch = "main"
}

resource "cloudflare_pages_domain" "site" {
  count = var.manage_pages && var.site_hostname != "" ? 1 : 0

  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.site[0].name
  name         = var.site_hostname
}

# CNAME for the custom domain → the Pages project.
resource "cloudflare_dns_record" "site" {
  count = var.manage_pages && var.site_hostname != "" ? 1 : 0

  zone_id = var.zone_id
  name    = var.site_hostname
  type    = "CNAME"
  content = "${var.pages_project_name}.pages.dev"
  proxied = true
  ttl     = 1
}
