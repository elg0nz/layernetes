output "tunnel_id" {
  description = "ID of the shared Cloudflare Tunnel."
  value       = cloudflare_zero_trust_tunnel_cloudflared.shared.id
}

output "tunnel_cname" {
  description = "The <id>.cfargotunnel.com target the public hostnames CNAME to."
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.shared.id}.cfargotunnel.com"
}

output "tunnel_token" {
  description = "Connector token for the in-cluster cloudflared Deployment. Feed into Secret ll-cloudflared-token (key: token)."
  value       = data.cloudflare_zero_trust_tunnel_cloudflared_token.shared.token
  sensitive   = true
}
