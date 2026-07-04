#!/usr/bin/env bash
# Configure every kiac node's containerd to trust a plain-HTTP OCI registry
# (the in-cluster Gitea registry) — the kiac equivalent of the README's
# k3s/Colima/kind insecure-registry instructions.
#
#   hack/kiac-registry-trust.sh <registry-host> [direct-cluster-ip] [cluster-prefix]
#   e.g. hack/kiac-registry-trust.sh gitea.192.168.64.200.sslip.io 10.96.100.100
#
# If direct-cluster-ip is given (the registryDirect Service IP from
# ll-infra), the registry hostname is also pinned to it in each node's
# /etc/hosts, so node image pulls bypass the ingress controller.
set -euo pipefail

REGISTRY=${1:?usage: kiac-registry-trust.sh <registry-host> [direct-cluster-ip] [cluster-prefix]}
DIRECT_IP=${2:-}
PREFIX=${3:-kiac-}

NODES=$(container ls --format json | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    if c["id"].startswith(sys.argv[1]) and c["status"]["state"] == "running":
        print(c["id"])
' "$PREFIX")

[ -n "$NODES" ] || { echo "no running nodes matching prefix '$PREFIX'" >&2; exit 1; }

for node in $NODES; do
  echo "→ $node"
  container exec "$node" sh -c "
    set -eu
    grep -q 'config_path = \"/etc/containerd/certs.d\"' /etc/containerd/config.toml || {
      printf '\n[plugins.\"io.containerd.grpc.v1.cri\".registry]\n  config_path = \"/etc/containerd/certs.d\"\n' >> /etc/containerd/config.toml
    }
    mkdir -p '/etc/containerd/certs.d/$REGISTRY'
    printf 'server = \"http://$REGISTRY\"\n\n[host.\"http://$REGISTRY\"]\n  capabilities = [\"pull\", \"resolve\"]\n' \
      > '/etc/containerd/certs.d/$REGISTRY/hosts.toml'
    if [ -n '$DIRECT_IP' ]; then
      sed -i '/ $REGISTRY\$/d' /etc/hosts
      echo '$DIRECT_IP $REGISTRY' >> /etc/hosts
    fi
    systemctl restart containerd
  "
done
echo "containerd on all nodes now trusts http://$REGISTRY"
