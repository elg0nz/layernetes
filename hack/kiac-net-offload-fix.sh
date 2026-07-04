#!/usr/bin/env bash
# kiac VMs (Apple Virtualization framework + vmnet) mishandle TSO/GSO/GRO
# super-frames on FORWARDED traffic: node-local TCP is fine, but bulk
# pod-to-pod traffic crossing nodes (and anything relayed by an in-cluster
# proxy, e.g. ingress-nginx) stalls after a few MB. Disabling NIC offloads
# on each node's uplink fixes it (measured: stalled -> ~600 MB/s).
#
#   hack/kiac-net-offload-fix.sh [cluster-prefix]
#
# Not persistent across VM restarts — rerun after `kiac` recreates nodes.
set -euo pipefail

PREFIX=${1:-kiac-}

NODES=$(container ls --format json | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    if c["id"].startswith(sys.argv[1]) and c["status"]["state"] == "running":
        print(c["id"])
' "$PREFIX")

[ -n "$NODES" ] || { echo "no running nodes matching prefix '$PREFIX'" >&2; exit 1; }

for node in $NODES; do
  container exec "$node" sh -c 'ethtool -K eth0 tso off gso off gro off >/dev/null 2>&1; echo "$(hostname): eth0 tso/gso/gro off"'
done
