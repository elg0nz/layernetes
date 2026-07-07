# Gate the Gitea signup page behind GitHub identity (see the Onboarding guide).
# Only created when a GitHub identity provider ID is supplied.
locals {
  access_enabled = var.github_identity_provider_id != "" ? 1 : 0
  gitea_hostname = "gitea.${var.platform_domain}"
}

resource "cloudflare_zero_trust_access_policy" "gitea_signup" {
  count = local.access_enabled

  account_id = var.cloudflare_account_id
  name       = "Layernetes — Gitea signup (GitHub org)"
  decision   = "allow"

  include = [
    {
      github_organization = {
        identity_provider_id = var.github_identity_provider_id
        name                 = var.github_organization
      }
    },
  ]
}

resource "cloudflare_zero_trust_access_application" "gitea_signup" {
  count = local.access_enabled

  account_id = var.cloudflare_account_id
  name       = "Layernetes — Gitea signup"
  type       = "self_hosted"
  # Scope the Access app to just the signup path, so git traffic and the CLI
  # (which carry their own auth) stay open.
  domain = "${local.gitea_hostname}/user/sign_up"

  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.gitea_signup[0].id
      precedence = 1
    },
  ]
}
