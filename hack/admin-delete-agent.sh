#!/usr/bin/env bash
# Force-delete an LLAgent as cluster admin, bypassing ll-api/owner auth.
# Anyone holding the cluster kubeconfig can run this — use it when an agent
# is stuck (deploy won't start, namespace won't clean up) and the owner can't
# `llnate delete` it themselves.
#
#   hack/admin-delete-agent.sh <llagent-name>
#   hack/admin-delete-agent.sh -k /path/to.kubeconfig <llagent-name>
#
# <llagent-name> is the LLAgent CR name (kubectl get llagent -n layernetes),
# not the pod name — e.g. "testing-foo-berry-serious-agent".
#
# Deletes the LLAgent CR (the operator's finalizer tears down the
# agent-<name> namespace/deployment/ingress). If the namespace is still
# Terminating after $WAIT_SECONDS (default 60s) — usually a stuck finalizer —
# clears the namespace's own finalizers to force it away.
set -euo pipefail

KUBECONFIG_PATH="$(dirname "$0")/../kiac-kiac.kubeconfig"
WAIT_SECONDS=${WAIT_SECONDS:-60}

while getopts "k:" opt; do
  case "$opt" in
    k) KUBECONFIG_PATH=$OPTARG ;;
    *) echo "usage: $0 [-k kubeconfig] <llagent-name>" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))

[ $# -eq 1 ] || { echo "usage: $0 [-k kubeconfig] <llagent-name>" >&2; exit 1; }
name=$1
ns="agent-$name"

export KUBECONFIG=$KUBECONFIG_PATH

if ! kubectl get llagent "$name" -n layernetes >/dev/null 2>&1; then
  echo "no LLAgent named '$name' in namespace layernetes" >&2
  exit 1
fi

echo "deleting LLAgent/$name ..."
if kubectl delete llagent "$name" -n layernetes --wait=true --timeout="${WAIT_SECONDS}s"; then
  echo "done."
  exit 0
fi

echo "LLAgent delete timed out — namespace $ns is likely stuck Terminating." >&2
if kubectl get ns "$ns" >/dev/null 2>&1; then
  echo "clearing finalizers on namespace/$ns to force cleanup ..." >&2
  kubectl get ns "$ns" -o json \
    | jq '.spec.finalizers = []' \
    | kubectl replace --raw "/api/v1/namespaces/$ns/finalize" -f -
  echo "namespace/$ns finalized." >&2
fi
