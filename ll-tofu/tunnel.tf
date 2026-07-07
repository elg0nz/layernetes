locals {
  # Public hostnames served through the shared tunnel, each forwarded to the
  # in-cluster ingress controller (which then routes by Host header). Two
  # wildcards: one for the per-<sha> agent hostnames, one for the single-label
  # platform hostnames (gitea., api., …). Adjust to match your real routing.
  tunnel_hostnames = {
    agents   = "*.agents.${var.platform_domain}"
    platform = "*.${var.platform_domain}"
  }
}

# The shared Cloudflare Tunnel. `config_src = "cloudflare"` makes it a
# remotely-managed tunnel: the connector (the in-cluster `cloudflared`
# Deployment from ll-infra) just runs with the token, and the ingress config
# lives on the Cloudflare side — managed here by the *_config resource below.
resource "cloudflare_zero_trust_tunnel_cloudflared" "shared" {
  account_id = var.cloudflare_account_id
  name       = var.tunnel_name
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "shared" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.shared.id

  config = {
    ingress = concat(
      [for key, hostname in local.tunnel_hostnames : {
        hostname = hostname
        service  = var.origin_service
      }],
      # Catch-all: required as the final ingress rule.
      [{ service = "http_status:404" }],
    )
  }
}

# The connector token. Feed this into the in-cluster secret consumed by the
# ll-infra `cloudflared` Deployment (Secret `ll-cloudflared-token`, key `token`).
data "cloudflare_zero_trust_tunnel_cloudflared_token" "shared" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.shared.id
}

# Proxied CNAMEs pointing each public hostname at the tunnel.
resource "cloudflare_dns_record" "tunnel" {
  for_each = local.tunnel_hostnames

  zone_id = var.zone_id
  name    = each.value
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.shared.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
}
