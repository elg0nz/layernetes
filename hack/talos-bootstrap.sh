#!/usr/bin/env bash
# Bring Layernetes up on a fresh Talos cluster in one run.
#
#   hack/talos-bootstrap.sh --domain layernetes.example.com [--users "alice bob"]
#
# --domain is the ONE thing you must supply: hostnames become gitea.<domain>,
# api.<domain>, agents.<domain> (use your own domain, or a
# <tailscale-ip>.sslip.io base). Everything else lives in
# ll-infra/values-talos.yaml.
#
# Pass --lb-pool "<start>-<end>" to install MetalLB and hand the ingress
# controller a real LoadBalancer IP on your LAN (reach the platform directly
# for now; Tailscale / Cloudflare front it in a future version). Without it,
# ingress-nginx is installed as NodePort and reachability is yours to wire.
# See docs/TALOS.md, plus the required Talos machine-config registry patch.
#
# The run is phased and idempotent — safe to re-run:
#   0 preflight        tools, cluster context, nodes Ready
#   1 storage          install local-path-provisioner if no default StorageClass
#   2 network          install MetalLB (if --lb-pool) + ingress-nginx
#   3 namespace        create it + label privileged (the CI dind sidecar needs it)
#   4 secrets          generate admin password + runner token (once)
#   5 gitea-first      helm install with ll-api/ll-operator OFF; wait for Gitea
#   6 platform images  build ll-api/ll-operator/llagent-base, push into Gitea
#   7 platform         helm upgrade with ll-api/ll-operator ON; wait for rollout
#   8 users            provision initial Gitea logins (if --users given)
#
# Flags: --lb-pool "192.168.1.240-192.168.1.250" (enable MetalLB + a LB IP) ·
# --namespace NS (default layernetes) · --release NAME (default layernetes) ·
# --skip-storage · --skip-ingress · --skip-images (point the values at prebuilt
# images instead) · --yes (don't prompt on the k8s context) ·
# --values-extra FILE (an extra `-f` overlay layered on top of values-talos.yaml,
# after it and the secret file so it wins — e.g. ll-infra/values-wtp.yaml to
# turn on cloudflared and the wtp.io dual hostnames. host_sets() --set flags
# still take precedence, so the canonical sslip.io hostnames stay intact).
set -euo pipefail

# ── config / flags ───────────────────────────────────────────────────────────
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHART="$REPO_ROOT/ll-infra"
VALUES="$CHART/values-talos.yaml"
SECRET_VALUES="$CHART/values-talos.secret.yaml"

DOMAIN=""
NAMESPACE="layernetes"
RELEASE="layernetes"
USERS=""
LB_POOL="" # e.g. "192.168.1.240-192.168.1.250"; set → install MetalLB + a LB IP
VALUES_EXTRA="" # optional extra -f overlay layered on top of values-talos.yaml
ADMIN_USER="${GITEA_ADMIN_USER:-layernetes-admin}"
INGRESS_CLASS="nginx"
SKIP_STORAGE=0 SKIP_INGRESS=0 SKIP_IMAGES=0 ASSUME_YES=0

# Pinned upstream manifests. Ingress uses the LoadBalancer ("cloud") variant
# when MetalLB is in play, else bare-metal/NodePort.
INGRESS_NGINX_LB="https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml"
INGRESS_NGINX_NODEPORT="https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/baremetal/deploy.yaml"
METALLB_MANIFEST="https://raw.githubusercontent.com/metallb/metallb/v0.14.9/config/manifests/metallb-native.yaml"
LOCAL_PATH_MANIFEST="https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml"
LOCAL_PATH_DIR="/var/local-path-provisioner" # /var is writable on Talos; /opt is not

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --release) RELEASE="$2"; shift 2 ;;
    --users) USERS="$2"; shift 2 ;;
    --lb-pool) LB_POOL="$2"; shift 2 ;;
    --values-extra) VALUES_EXTRA="$2"; shift 2 ;;
    --ingress-class) INGRESS_CLASS="$2"; shift 2 ;;
    --skip-storage) SKIP_STORAGE=1; shift ;;
    --skip-ingress) SKIP_INGRESS=1; shift ;;
    --skip-images) SKIP_IMAGES=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

GITEA_HOST="gitea.${DOMAIN}"
API_HOST="api.${DOMAIN}"
AGENTS_HOST="agents.${DOMAIN}"
GITEA_DEPLOY="${RELEASE}-gitea"

log()  { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
kc()   { kubectl --namespace "$NAMESPACE" "$@"; }

# ── 0. preflight ─────────────────────────────────────────────────────────────
log "Phase 0 · preflight"
for bin in kubectl helm openssl; do command -v "$bin" >/dev/null || die "missing required tool: $bin"; done
[ "$SKIP_IMAGES" = 1 ] || command -v docker >/dev/null || die "docker is required to build/push platform images (or pass --skip-images)"
[ -n "$DOMAIN" ] || die "pass --domain <your-domain> (e.g. layernetes.example.com or 100.x.y.z.sslip.io)"
[ -z "$VALUES_EXTRA" ] || [ -f "$VALUES_EXTRA" ] || die "--values-extra file not found: $VALUES_EXTRA"

CTX=$(kubectl config current-context) || die "no current kubectl context"
info "kubectl context : $CTX"
info "namespace       : $NAMESPACE"
info "domain          : $DOMAIN  (gitea/api/agents.$DOMAIN)"
if [ "$ASSUME_YES" != 1 ]; then
  read -r -p "  Install Layernetes into context '$CTX'? [y/N] " ans
  [ "$ans" = y ] || [ "$ans" = Y ] || die "aborted"
fi
kubectl get nodes >/dev/null || die "cluster '$CTX' is not reachable"
if kubectl get nodes --no-headers | grep -qvw Ready; then
  info "warning: not all nodes are Ready — continuing anyway"
fi

helm repo add gitea https://dl.gitea.com/charts/ >/dev/null 2>&1 || true
helm repo update gitea >/dev/null 2>&1 || true
log "building chart dependencies"
helm dependency build "$CHART" >/dev/null

# ── 1. storage ───────────────────────────────────────────────────────────────
log "Phase 1 · storage"
if kubectl get sc -o jsonpath='{range .items[*]}{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}{"\n"}{end}' 2>/dev/null | grep -qx true; then
  info "a default StorageClass already exists — skipping"
elif [ "$SKIP_STORAGE" = 1 ]; then
  info "--skip-storage set; ensure a default StorageClass exists for Gitea's PVC"
else
  info "no default StorageClass — installing local-path-provisioner"
  kubectl apply -f "$LOCAL_PATH_MANIFEST" >/dev/null
  # Talos: root fs is read-only; put volumes under /var, and the helper pods
  # mount hostPath as root, so the namespace must allow privileged pods.
  kubectl label ns local-path-storage pod-security.kubernetes.io/enforce=privileged --overwrite >/dev/null
  kubectl -n local-path-storage patch configmap local-path-config --type merge -p \
    "{\"data\":{\"config.json\":\"{\\\"nodePathMap\\\":[{\\\"node\\\":\\\"DEFAULT_PATH_FOR_NON_LISTED_NODES\\\",\\\"paths\\\":[\\\"${LOCAL_PATH_DIR}\\\"]}]}\"}}" >/dev/null
  kubectl -n local-path-storage rollout restart deploy/local-path-provisioner >/dev/null
  kubectl patch storageclass local-path -p \
    '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}' >/dev/null
  kubectl -n local-path-storage rollout status deploy/local-path-provisioner --timeout=120s
fi

# ── 2. network: MetalLB + ingress ────────────────────────────────────────────
log "Phase 2 · load balancer + ingress"
if [ -n "$LB_POOL" ]; then
  if kubectl get ns metallb-system >/dev/null 2>&1 && kubectl -n metallb-system get deploy controller >/dev/null 2>&1; then
    info "MetalLB already installed — (re)applying address pool $LB_POOL"
  else
    info "installing MetalLB"
    kubectl apply -f "$METALLB_MANIFEST" >/dev/null
    # MetalLB's own namespace ships privileged PSA labels; belt-and-suspenders.
    kubectl label ns metallb-system pod-security.kubernetes.io/enforce=privileged --overwrite >/dev/null 2>&1 || true
  fi
  info "waiting for the MetalLB controller + webhook"
  kubectl -n metallb-system rollout status deploy/controller --timeout=180s
  # The IPAddressPool/L2Advertisement CRs are gated by MetalLB's admission
  # webhook, which needs a few seconds after the controller is Ready.
  for i in $(seq 1 30); do
    if kubectl apply -f - >/dev/null 2>&1 <<EOF
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata: {name: layernetes-pool, namespace: metallb-system}
spec: {addresses: [$LB_POOL]}
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata: {name: layernetes-l2, namespace: metallb-system}
spec: {ipAddressPools: [layernetes-pool]}
EOF
    then break; fi
    [ "$i" = 30 ] && die "MetalLB webhook never accepted the address pool"
    sleep 2
  done
  info "MetalLB address pool 'layernetes-pool' → $LB_POOL"
  INGRESS_MANIFEST="$INGRESS_NGINX_LB"
  INGRESS_KIND="LoadBalancer (via MetalLB)"
else
  INGRESS_MANIFEST="$INGRESS_NGINX_NODEPORT"
  INGRESS_KIND="NodePort (no --lb-pool given)"
fi

if kubectl get ingressclass "$INGRESS_CLASS" >/dev/null 2>&1; then
  info "IngressClass '$INGRESS_CLASS' already present — skipping ingress install"
elif [ "$SKIP_INGRESS" = 1 ]; then
  info "--skip-ingress set; the '$INGRESS_CLASS' ingress class must be served by something (e.g. the Tailscale operator)"
else
  info "installing ingress-nginx — $INGRESS_KIND"
  kubectl apply -f "$INGRESS_MANIFEST" >/dev/null
  kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=180s
fi

# ── 3. namespace + pod security ──────────────────────────────────────────────
log "Phase 3 · namespace"
kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE" >/dev/null
# The Actions runner's docker-in-docker sidecar runs privileged; Talos enforces
# PodSecurity 'baseline' on non-exempt namespaces, which would reject it.
kubectl label ns "$NAMESPACE" pod-security.kubernetes.io/enforce=privileged --overwrite >/dev/null
info "namespace '$NAMESPACE' labelled pod-security.kubernetes.io/enforce=privileged"

# ── 4. secrets ───────────────────────────────────────────────────────────────
log "Phase 4 · secrets"
if [ -f "$SECRET_VALUES" ]; then
  info "$SECRET_VALUES exists — reusing"
else
  info "generating admin password + runner token → $SECRET_VALUES (gitignored)"
  ADMIN_PASS=$(openssl rand -hex 16)
  RUNNER_TOKEN=$(openssl rand -hex 20) # exactly 40 alphanumeric chars
  cat > "$SECRET_VALUES" <<EOF
# Generated by hack/talos-bootstrap.sh — DO NOT COMMIT (gitignored).
# Recreate/rotate by deleting this file and re-running the script (then
# helm upgrade will re-sync the credentials).
giteaAdmin:
  password: "${ADMIN_PASS}"
actRunner:
  token: "${RUNNER_TOKEN}"
EOF
  chmod 600 "$SECRET_VALUES"
fi
ADMIN_PASS=$(grep -A1 '^giteaAdmin:' "$SECRET_VALUES" | grep 'password:' | sed -E 's/.*password:[[:space:]]*"?([^"]+)"?.*/\1/')
[ -n "$ADMIN_PASS" ] || die "could not read admin password from $SECRET_VALUES"

# helm --set overrides derived from --domain (so you never edit the values file)
host_sets() {
  echo "--set-string global.hosts.gitea=$GITEA_HOST"
  echo "--set-string global.hosts.api=$API_HOST"
  echo "--set-string global.hosts.agents=$AGENTS_HOST"
  echo "--set-string llApi.image.repository=$GITEA_HOST/layernetes/ll-api"
  echo "--set-string llApi.llagentBaseImage=$GITEA_HOST/layernetes/llagent-base:latest"
  echo "--set-string llOperator.image.repository=$GITEA_HOST/layernetes/ll-operator"
  echo "--set-string actRunner.dind.insecureRegistries[0]=$GITEA_HOST"
  echo "--set-string actRunner.dind.insecureRegistries[1]=${RELEASE}-gitea-http.$NAMESPACE.svc.cluster.local:3000"
  echo "--set-string gitea.ingress.hosts[0].host=$GITEA_HOST"
  echo "--set-string gitea.gitea.config.server.ROOT_URL=http://$GITEA_HOST/"
  echo "--set-string gitea.gitea.config.server.DOMAIN=$GITEA_HOST"
}
read -r -a HOST_SETS <<< "$(host_sets | tr '\n' ' ')"

# An optional overlay goes after the base + secret files (so it wins on deep
# merge) but the HOST_SETS --set flags still beat any -f, keeping the canonical
# --domain hostnames intact regardless of what the overlay adds.
EXTRA_VALUES_ARGS=()
[ -n "$VALUES_EXTRA" ] && EXTRA_VALUES_ARGS=(-f "$VALUES_EXTRA")

helm_install() { # extra --set args passed as "$@"
  helm upgrade --install "$RELEASE" "$CHART" -n "$NAMESPACE" --create-namespace \
    -f "$VALUES" -f "$SECRET_VALUES" "${EXTRA_VALUES_ARGS[@]}" "${HOST_SETS[@]}" "$@"
}

# ── 5. Gitea first ───────────────────────────────────────────────────────────
log "Phase 5 · Gitea (ll-api/ll-operator held back until their images exist)"
helm_install --set llApi.enabled=false --set llOperator.enabled=false
info "waiting for Gitea to roll out"
kc rollout status "deploy/$GITEA_DEPLOY" --timeout=300s

# ── 6. platform images ───────────────────────────────────────────────────────
if [ "$SKIP_IMAGES" = 1 ]; then
  log "Phase 6 · platform images — skipped (--skip-images)"
  info "values must point ll-api/ll-operator at images your nodes can already pull"
else
  log "Phase 6 · build + push platform images into Gitea"
  # Push through a localhost port-forward: Docker trusts localhost as insecure
  # automatically, so no daemon 'insecure-registries' config is needed. The
  # repo path (layernetes/*) is what nodes later pull as $GITEA_HOST/layernetes/*.
  kc port-forward "deploy/$GITEA_DEPLOY" 3000:3000 >/dev/null 2>&1 &
  PF_PID=$!
  trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
  info "waiting for the Gitea API"
  for i in $(seq 1 60); do
    curl -fsS http://localhost:3000/api/v1/version >/dev/null 2>&1 && break
    [ "$i" = 60 ] && die "Gitea API did not come up on the port-forward"
    sleep 2
  done
  info "ensuring the 'layernetes' registry org exists"
  org_code=$(curl -sS -o /dev/null -u "$ADMIN_USER:$ADMIN_PASS" \
    -X POST http://localhost:3000/api/v1/orgs \
    -H 'Content-Type: application/json' -d '{"username":"layernetes"}' \
    -w '%{http_code}' 2>/dev/null || true)
  case "$org_code" in
    201) info "  created org 'layernetes'" ;;
    422) info "  org 'layernetes' already exists" ;;
    *)   info "  unexpected response ($org_code) creating org — continuing" ;;
  esac
  echo "$ADMIN_PASS" | docker login localhost:3000 -u "$ADMIN_USER" --password-stdin >/dev/null
  for comp in ll-api ll-operator llagent-base; do
    info "building + pushing $comp"
    docker build -q -t "localhost:3000/layernetes/$comp:latest" "$REPO_ROOT/$comp" >/dev/null
    docker push "localhost:3000/layernetes/$comp:latest" >/dev/null
  done
  docker logout localhost:3000 >/dev/null 2>&1 || true
  kill "$PF_PID" 2>/dev/null || true
  trap - EXIT
fi

# ── 7. full platform ─────────────────────────────────────────────────────────
log "Phase 7 · enable ll-api + ll-operator"
helm_install
info "waiting for platform rollouts"
kc rollout status deploy/ll-api --timeout=180s
kc rollout status deploy/ll-operator --timeout=180s
kc rollout status deploy/gitea-act-runner --timeout=180s

# ── 8. users ─────────────────────────────────────────────────────────────────
if [ -n "$USERS" ]; then
  log "Phase 8 · provision Gitea logins: $USERS"
  kc port-forward "deploy/$GITEA_DEPLOY" 3000:3000 >/dev/null 2>&1 &
  PF_PID=$!
  trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
  for i in $(seq 1 30); do curl -fsS http://localhost:3000/api/v1/version >/dev/null 2>&1 && break; sleep 2; done
  GITEA_URL=http://localhost:3000 GITEA_ADMIN="$ADMIN_USER" GITEA_ADMIN_PASSWORD="$ADMIN_PASS" \
    "$REPO_ROOT/hack/provision-users.sh" $USERS || true
  kill "$PF_PID" 2>/dev/null || true
  trap - EXIT
fi

# ── done ─────────────────────────────────────────────────────────────────────
log "Layernetes is installed on '$CTX'."
cat <<EOF

  Gitea   : http://$GITEA_HOST/        (admin: $ADMIN_USER — password in $SECRET_VALUES)
  ll-api  : http://$API_HOST/
  agents  : http://<sha>.$AGENTS_HOST/

  Point those hostnames at the ingress controller's Service:
      kubectl -n ingress-nginx get svc ingress-nginx-controller
$(if [ -n "$LB_POOL" ]; then
  printf '  MetalLB assigns it an EXTERNAL-IP from %s — make *.%s resolve to\n  that IP (LAN DNS, or a <IP>.sslip.io domain). Tailscale / Cloudflare can\n  front it in a future version.' "$LB_POOL" "$DOMAIN"
else
  printf '  It is a NodePort Service (no --lb-pool) — reach it on a node IP:nodeport,\n  or wire Tailscale / a LoadBalancer. Re-run with --lb-pool to get a LAN IP.'
fi)

  IMPORTANT — before 'llnate push' can deploy agents, every Talos node's
  containerd must trust the plain-HTTP in-cluster registry. Apply the
  machine-config patch in docs/TALOS.md ("Trusting the in-cluster registry").

  Then, from a machine that can reach the API:
      export LLNATE_API_URL=http://$API_HOST
      llnate login && llnate init hello-agent && cd hello-agent && llnate push
EOF
