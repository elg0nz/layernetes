terraform {
  required_version = ">= 1.6"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # State backend. Defaults to local state (works out of the box; the state
  # file stays in this directory and is gitignored). For a team, move state to
  # a remote backend — Cloudflare R2 via the S3-compatible backend is a nice
  # self-hosted fit. To switch, uncomment and fill in the block below, then run
  # `tofu init -migrate-state`. See README.md → "State backend".
  #
  # backend "s3" {
  #   bucket                      = "ll-tofu-state"
  #   key                         = "cloudflare/terraform.tfstate"
  #   region                      = "auto"
  #   endpoints                   = { s3 = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" }
  #   skip_credentials_validation = true
  #   skip_region_validation      = true
  #   skip_requesting_account_id  = true
  #   skip_s3_checksum            = true
  #   use_path_style              = true
  #   # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY = an R2 API token (S3 auth).
  # }
}
