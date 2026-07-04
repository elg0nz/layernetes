#!/usr/bin/env bash
# Pre-provision platform logins by creating Gitea users via the admin API.
# (Self-registration is disabled; a "login" is just a Gitea account — the
# user's PAT, age keypair, and repo are provisioned on first `llnate login`.)
#
#   GITEA_URL=http://gitea.192.168.64.200.sslip.io \
#   GITEA_ADMIN=layernetes-admin GITEA_ADMIN_PASSWORD=... \
#     hack/provision-users.sh alice bob carol
#
# Prints one `username password` line per created user. Existing users are
# left untouched (reported as "exists"). Passwords: $PASSWORD if set (same
# for all), otherwise random per user.
set -euo pipefail

GITEA_URL=${GITEA_URL:?set GITEA_URL (e.g. http://gitea.192.168.64.200.sslip.io)}
GITEA_ADMIN=${GITEA_ADMIN:?set GITEA_ADMIN}
GITEA_ADMIN_PASSWORD=${GITEA_ADMIN_PASSWORD:?set GITEA_ADMIN_PASSWORD}
EMAIL_DOMAIN=${EMAIL_DOMAIN:-users.learninglayer.ai}

[ $# -gt 0 ] || { echo "usage: provision-users.sh <username>..." >&2; exit 1; }

for user in "$@"; do
  pass=${PASSWORD:-$(openssl rand -hex 10)}
  code=$(curl -s -o /tmp/provision-user.out -w '%{http_code}' \
    -u "$GITEA_ADMIN:$GITEA_ADMIN_PASSWORD" \
    -X POST "$GITEA_URL/api/v1/admin/users" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$user\",\"email\":\"$user@$EMAIL_DOMAIN\",\"password\":\"$pass\",\"must_change_password\":false}")
  case "$code" in
    201) echo "$user $pass" ;;
    422) echo "$user (exists, unchanged)" >&2 ;;
    *)   echo "$user FAILED ($code): $(cat /tmp/provision-user.out)" >&2; exit 1 ;;
  esac
done
rm -f /tmp/provision-user.out
