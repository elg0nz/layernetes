# Rolling out Layernetes on Talos

Stand the whole platform up on a fresh [Talos Linux](https://www.talos.dev/)
cluster in three steps: **pick a domain → run one script → verify.** Reachability
(Tailscale now, Cloudflare later) is handled outside the cluster; this guide gets
Layernetes running *inside* it, with Gitea as the auth layer.

> Prefer the direct path first. Once it's up you can optionally hand ongoing
> management to ArgoCD — see [GitOps with ArgoCD](#gitops-with-argocd).

---

## What the script sets up

Talos ships no ingress controller, no LoadBalancer, and no default
StorageClass, and it enforces Pod Security. `hack/talos-bootstrap.sh` fills every
one of those gaps, in idempotent phases (safe to re-run):

| Phase | Does |
| --- | --- |
| 0 preflight | checks tools, prints the kubectl context, waits for nodes |
| 1 storage | installs local-path-provisioner (Talos paths under `/var`) if no default StorageClass |
| 2 ingress | installs ingress-nginx (bare-metal / NodePort) if the `nginx` class is missing |
| 3 namespace | creates `layernetes`, labels it `pod-security…/enforce=privileged` (the CI docker-in-docker sidecar needs it) |
| 4 secrets | generates the Gitea admin password + Actions runner token once, into a gitignored file |
| 5 Gitea-first | installs the chart with `ll-api`/`ll-operator` **off**, so Gitea + its registry come up |
| 6 images | builds `ll-api`, `ll-operator`, `llagent-base` and pushes them into the in-cluster Gitea registry |
| 7 platform | re-runs Helm with `ll-api`/`ll-operator` **on**, pointing at those freshly-pushed images |
| 8 users | provisions initial Gitea logins (if you pass `--users`) |

Phases 5–7 are split on purpose: on a brand-new cluster the platform images
don't exist yet — they live in the Gitea registry that Helm is about to install
(chicken-and-egg). The script brings Gitea up first, pushes the images into it,
then enables the components that consume them.

---

## Prerequisites

- A running Talos cluster and a working `kubeconfig` (`kubectl get nodes` → `Ready`).
- Local tools: `kubectl`, `helm`, `docker`, `openssl`, `git`. (`docker` only if
  you let the script build images — the default.)
- A domain (or a `<tailscale-ip>.sslip.io` base) that will resolve to the
  cluster's ingress. You wire the actual routing; see
  [Reachability](#reachability-tailscale--cloudflare).

---

## 1 · Pick your domain

There is nothing to edit for the scripted path — you pass the domain as a flag.
Hostnames are derived as `gitea.<domain>`, `api.<domain>`, `agents.<domain>`.

```sh
# examples:
#   --domain layernetes.example.com        → gitea.layernetes.example.com, …
#   --domain 100.101.102.103.sslip.io      → gitea.100.101.102.103.sslip.io, …
```

Everything else already lives in `ll-infra/values-talos.yaml` (light single-node
Gitea, `cloudflared` off, self-registration off). Only edit that file directly if
you're taking the [ArgoCD](#gitops-with-argocd) path.

## 2 · Run the bootstrap

```sh
hack/talos-bootstrap.sh --domain layernetes.example.com --users "alice bob"
```

It prints the context it's about to install into and asks for confirmation (pass
`--yes` to skip). On success it prints the platform URLs and where the generated
admin password lives (`ll-infra/values-talos.secret.yaml`, gitignored).

Useful flags: `--skip-ingress` (your cluster already routes the `nginx` class —
e.g. the Tailscale operator serves ingress), `--skip-storage` (you already have a
default StorageClass), `--skip-images` (you publish `ll-api`/`ll-operator`
elsewhere and pointed the values at them), `--namespace` / `--release`.

## 3 · Trust the in-cluster registry, then verify

The in-cluster Gitea registry is plain HTTP, so **every Talos node's containerd
must be told to trust it** — otherwise agent image pulls fail with an HTTPS
error. This is a node-OS setting, so it's a Talos machine-config patch you apply
with `talosctl` (the script can't do it for you):

```yaml
# talos-registry.patch.yaml  — replace gitea.layernetes.example.com with your host
machine:
  registries:
    mirrors:
      gitea.layernetes.example.com:
        endpoints:
          - http://gitea.layernetes.example.com   # http:// → plain-HTTP pulls
```

```sh
talosctl patch mc --patch @talos-registry.patch.yaml   # add -n <node> per node if needed
```

If your nodes can't resolve the hostname (e.g. it's a Tailscale name that only
your laptop knows), also pin it to the ingress node's IP:

```yaml
machine:
  network:
    extraHostEntries:
      - ip: 10.0.0.5                     # a node IP the registry is reachable on
        aliases: [gitea.layernetes.example.com]
```

Then confirm the platform is healthy:

```sh
kubectl -n layernetes get pods            # gitea, ll-api, ll-operator, gitea-act-runner all Running
kubectl -n layernetes get ingress         # ll-api + gitea hosts
```

And run the real end-to-end flow (the acceptance test):

```sh
export LLNATE_API_URL=http://api.layernetes.example.com
llnate login                              # a Gitea account (admin, or a --users login)
llnate init hello-agent && cd hello-agent
llnate keys && llnate push                # push → Actions build → operator deploy
curl http://<sha>.agents.layernetes.example.com/healthz
```

---

## Reachability (Tailscale / Cloudflare)

The script installs an in-cluster **ingress controller** (the router for the
`<sha>.agents.*` hostnames) but deliberately sets up **no LoadBalancer** — how
traffic reaches the cluster is yours to wire:

- **Tailscale (now).** Reach the ingress over your tailnet. Either expose the
  `ingress-nginx-controller` Service (its NodePort on a node's Tailscale IP, or
  via the [Tailscale Kubernetes operator](https://tailscale.com/kb/1236/kubernetes-operator)),
  and make `*.<domain>` resolve to it. If the Tailscale operator itself serves
  ingress, run the script with `--skip-ingress` and set the ingress class
  accordingly.
- **Cloudflare (later).** Re-enable `cloudflared` (it's off in
  `values-talos.yaml`), create the `ll-cloudflared-token` Secret, and point a
  Cloudflare Tunnel at the ingress controller — the production model in the
  repository README. Nothing else in the platform changes.

Because it's plain HTTP for now, `values-talos.yaml` uses `urlScheme: http`. Put
TLS (Cloudflare, or cert-manager) in front of the ingress when you're ready and
flip that to `https`.

---

## GitOps with ArgoCD

ArgoCD keeps the platform continuously reconciled from git. Two things it
**cannot** do, so the direct bootstrap still comes first: it doesn't build
container images (phase 6 seeds `ll-api`/`ll-operator`/`llagent-base` into the
Gitea registry), and it won't install the cluster prerequisites (storage,
ingress, the privileged-namespace label). Run the script once to get a working
cluster, then hand ongoing sync to ArgoCD if you want it.

**1 · Install ArgoCD.**

```sh
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server
```

**2 · Point the manifests at your fork and domain.** `ll-infra/argocd/` ships an
`AppProject` and an `Application`. Edit both to reference your repository, and set
the Application to layer `values-talos.yaml` with your hostnames. The credentials
must not live in git — supply them from a Secret via a private values file, or
[sealed-secrets](https://github.com/bitnami-labs/sealed-secrets); the snippet
below uses `valuesObject` inline for brevity, which is fine for a homelab but
commits secrets to git.

```yaml
# ll-infra/argocd/application.yaml (adapted)
spec:
  project: layernetes
  source:
    repoURL: https://github.com/<you>/layernetes.git   # your fork
    targetRevision: main
    path: ll-infra
    helm:
      valueFiles:
        - values.yaml
        - values-talos.yaml          # edit its hostnames + image repos to your domain
      valuesObject:
        cloudflared:
          enabled: false
        giteaAdmin:
          password: <from a Secret / sealed-secret — not plaintext in git>
        actRunner:
          token: <40 hex chars — likewise>
  destination:
    server: https://kubernetes.default.svc
    namespace: layernetes
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: [CreateNamespace=true, ServerSideApply=true]
```

Because `values-talos.yaml` is a static file (no `--domain` substitution),
replace `layernetes.example.com` in it with your domain — the three
`global.hosts.*`, the two image `repository:` fields + `llagentBaseImage`, the
`gitea.ingress.hosts[0].host`, and the gitea `ROOT_URL`/`DOMAIN`.

**3 · Apply.**

```sh
kubectl apply -f ll-infra/argocd/
```

ArgoCD adopts the Helm release and reconciles it from git on every push. The
`layernetes` namespace keeps the `pod-security…/enforce=privileged` label from
the bootstrap; if you let ArgoCD create the namespace fresh instead, add that
label yourself or the Actions runner won't schedule.

---

## Troubleshooting

- **`gitea-act-runner` pod won't start / `violates PodSecurity "baseline"`.** The
  namespace is missing the privileged label. `kubectl label ns layernetes
  pod-security.kubernetes.io/enforce=privileged --overwrite`.
- **Gitea PVC stuck `Pending`.** No default StorageClass. Re-run without
  `--skip-storage`, or mark one default:
  `kubectl patch storageclass <name> -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'`.
- **`llnate push` builds but the deploy never becomes Ready / ImagePullBackOff on
  an agent.** Node containerd doesn't trust the plain-HTTP registry — apply the
  machine-config patch in [step 3](#3--trust-the-in-cluster-registry-then-verify).
- **`docker push` in phase 6 fails.** The script pushes through a `localhost:3000`
  port-forward (Docker trusts `localhost` as insecure automatically). Make sure
  nothing else holds port 3000, and that Gitea rolled out (phase 5).
- **Ingress reachable in-cluster but not from your machine.** That's the
  reachability layer you own — see [above](#reachability-tailscale--cloudflare).
  `kubectl -n ingress-nginx get svc` shows the NodePorts to target.
