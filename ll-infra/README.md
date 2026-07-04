# ll-infra

Helm umbrella chart for the Layernetes platform, plus ArgoCD manifests for
GitOps deployment. What it installs:

| Component | Source | Purpose |
| --- | --- | --- |
| Gitea | [gitea helm chart](https://gitea.com/gitea/helm-chart) (dependency) | Git hosting, Gitea Actions, built-in OCI registry |
| `gitea-act-runner` | `templates/act-runner/` | Actions runner with docker-in-docker sidecar for image builds |
| `ll-api` | `templates/ll-api/` | Control-plane API (namespace-scoped RBAC over LLAgents + Secrets) |
| `ll-operator` | `templates/ll-operator/` | LLAgent reconciler (cluster-scoped RBAC for per-agent namespaces) |
| `cloudflared` | `templates/cloudflared/` | Production edge; disabled in `values-local.yaml` |
| `LLAgent` CRD | `crds/llagent.yaml` | The ll-api ⇄ ll-operator contract (see repository README) |

## Install (local)

```sh
helm dependency build ll-infra
helm install layernetes ./ll-infra -n layernetes --create-namespace \
  -f ll-infra/values-local.yaml
```

See the repository README ("Developing locally") for cluster setup, ingress
port-forwarding, and the end-to-end smoke test.

## Install (GitOps, production)

Apply the ArgoCD manifests into the cluster running ArgoCD:

```sh
kubectl apply -f ll-infra/argocd/
```

Before the first sync, create the tunnel-token Secret and override the dev
defaults (`giteaAdmin.password`, `actRunner.token`):

```sh
kubectl -n layernetes create secret generic ll-cloudflared-token \
  --from-literal=token=<cloudflare tunnel token>
```

## How the pieces are wired

- **Runner registration.** `actRunner.token` lands in the `ll-act-runner-token`
  Secret; the gitea subchart injects it as `GITEA_RUNNER_REGISTRATION_TOKEN`
  (Gitea pre-registers it) and the runner uses the same token to register.
  Must be exactly 40 alphanumeric characters.
- **Gitea admin.** `giteaAdmin.*` lands in the `ll-gitea-admin` Secret, used
  by the gitea subchart for the initial admin user and mounted into `ll-api`
  for repo/user provisioning.
- **Hostnames.** `global.hosts.*` + `global.urlScheme`/`urlPortSuffix` drive
  every externally visible URL (ll-api ingress, agent URLs built by
  ll-operator, Gitea clone URLs). The gitea subchart's ingress host and
  `ROOT_URL` are duplicated literally in the values files — keep them in sync.
- **Fixed resource names.** `ll-gitea-admin`, `ll-act-runner-token`, and
  `gitea-act-runner` are intentionally not release-prefixed: the first two are
  referenced literally from subchart values, the last from the README's
  troubleshooting commands. One release per namespace.
