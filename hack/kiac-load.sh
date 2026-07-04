#!/usr/bin/env bash
# Load a locally docker-built image into every node of a kiac cluster
# (the `kind load docker-image` equivalent for kiac, whose nodes run as
# apple/container VMs).
#
#   hack/kiac-load.sh <image:tag> [cluster-prefix]
#
# Example dev loop for platform components (see README "Working on
# individual components"):
#   docker build -t ll-api:dev ./ll-api
#   hack/kiac-load.sh ll-api:dev
#   kubectl -n layernetes rollout restart deploy/ll-api
set -euo pipefail

IMAGE=${1:?usage: kiac-load.sh <image:tag> [cluster-prefix]}
PREFIX=${2:-kiac-}

NODES=$(container ls --format json | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    if c["id"].startswith(sys.argv[1]) and c["status"]["state"] == "running":
        print(c["id"])
' "$PREFIX")

[ -n "$NODES" ] || { echo "no running nodes matching prefix '$PREFIX'" >&2; exit 1; }

TAR=$(mktemp -t kiac-load-XXXXXX).tar
trap 'rm -f "$TAR"' EXIT
docker save "$IMAGE" -o "$TAR"

for node in $NODES; do
  echo "→ $node"
  container exec -i "$node" ctr -n k8s.io images import - < "$TAR"
done
echo "loaded $IMAGE into: $NODES"
