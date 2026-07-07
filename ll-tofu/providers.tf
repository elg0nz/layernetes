provider "cloudflare" {
  # Prefer exporting the token as an environment variable instead of committing
  # it: `export CLOUDFLARE_API_TOKEN=…` (then leave api_token unset here), or
  # pass it via `var.cloudflare_api_token`.
  api_token = var.cloudflare_api_token != "" ? var.cloudflare_api_token : null
}
