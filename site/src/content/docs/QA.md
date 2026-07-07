---
title: QA guide
description: A hands-on walkthrough to verify every package and every contract in the README.
---

A hands-on walkthrough to verify every package and every contract in the
README. Ordered so each section builds on the previous one; run it top to
bottom for a full QA pass, or jump to a section after touching that package.

Throughout, `LB` is your ingress controller's MetalLB IP (this guide assumes
`192.168.64.200` — check with `kubectl -n ingress-nginx get svc`), and the
dev admin credentials are `layernetes-admin` / `layernetes-local-dev` (from
`ll-infra/values-local.yaml`).

## 0. Cluster preconditions (kiac)

```sh
kiac doctor && kubectl get nodes          # 4 nodes Ready
kubectl -n ingress-nginx get svc          # EXTERNAL-IP = 192.168.64.200
```

If the node VMs were restarted since setup, re-apply the node-level fixes
(they don't persist across VM restarts):

```sh
hack/kiac-net-offload-fix.sh
hack/kiac-registry-trust.sh gitea.192.168.64.200.sslip.io 10.96.100.100
```

**Symptom if you forget:** image pulls/pushes hang after a few MB while
small requests work — see the README troubleshooting entry.

## 1. Unit test suites

Every package ships its own venv-based suite. All four must be green:

```sh
cd ll-api        && .venv/bin/python -m pytest -q   # expect 27 passed
cd ../ll-operator && .venv/bin/python -m pytest -q  # expect 38 passed
cd ../llagent-base && .venv/bin/python -m pytest -q # expect 11 passed
cd ../llnate     && .venv/bin/pytest -q             # expect 28 passed
```

(First time on a fresh clone: `python3.12 -m venv .venv && .venv/bin/pip
install -e ".[dev]"` in each package; llagent-base uses
`pip install -r` of its test deps — see its README.)

## 2. ll-infra: chart hygiene and install

```sh
helm dependency build ll-infra
helm lint ll-infra && helm lint ll-infra -f ll-infra/values-local.yaml
```

Install (or upgrade) with the kiac overlay:

```sh
helm upgrade --install layernetes ./ll-infra -n layernetes --create-namespace \
  -f ll-infra/values-local.yaml -f ll-infra/values-kiac.yaml
kubectl -n layernetes get pods
```

**Pass:** 4 deployments all Running — `layernetes-gitea` (1/1),
`gitea-act-runner` (2/2 — runner + dind), `ll-api` (1/1), `ll-operator`
(1/1). The runner may restart once or twice at startup while dind boots;
that's the known benign race.

ArgoCD manifests are schema-valid (needs ArgoCD CRDs on some cluster, or
just eyeball): `kubectl apply --dry-run=server -f ll-infra/argocd/` on a
cluster with ArgoCD installed.

## 3. Platform plumbing: Gitea, registry, runner

```sh
# Gitea through the ingress, with the chart-managed admin secret
curl -s -u layernetes-admin:layernetes-local-dev \
  http://gitea.192.168.64.200.sslip.io/api/v1/version        # {"version":"1.26.x"}

# OCI registry alive (401 = auth challenge, correct for anonymous /v2/)
curl -s -o /dev/null -w '%{http_code}\n' http://gitea.192.168.64.200.sslip.io/v2/

# Base image present and anonymously pullable
skopeo inspect --tls-verify=false \
  docker://gitea.192.168.64.200.sslip.io/layernetes-admin/llagent-base:latest \
  --format '{{.Name}} {{.Architecture}}'                      # ... arm64

# Actions runner registered
kubectl -n layernetes logs deploy/gitea-act-runner -c runner | grep declare
# expect: "... declare successfully"
```

If `llagent-base:latest` is missing (fresh cluster), build and push it:

```sh
docker build -t llagent-base:dev ./llagent-base
kubectl -n layernetes port-forward svc/gitea-registry-direct 8099:80 &
skopeo copy --src-daemon-host unix://$HOME/.colima/default/docker.sock \
  --dest-tls-verify=false --dest-creds layernetes-admin:layernetes-local-dev \
  docker-daemon:llagent-base:dev docker://127.0.0.1:8099/layernetes-admin/llagent-base:latest
kill %1
```

Sanity-check the image arch matches your nodes (`arm64` on Apple silicon) —
a wrong-arch image manifests later as `sops: Exec format error` in the
agent pod.

## 4. LLAgent CRD contract

Round-trip the exact sample from the README:

```sh
kubectl apply -f - <<'EOF'
apiVersion: layernetes.learninglayer.ai/v1alpha1
kind: LLAgent
metadata: {name: qa-sample, namespace: layernetes}
spec: {owner: qa, repo: qa/sample, keySecretRef: age-key-qa}
EOF

# status subresource + printer columns
kubectl -n layernetes patch llagent qa-sample --subresource=status --type=merge \
  -p '{"status":{"phase":"Ready","url":"http://x.agents.example"}}'
kubectl -n layernetes get llagents        # PHASE/SHA/URL columns render

# phase enum is enforced
kubectl -n layernetes patch llagent qa-sample --subresource=status --type=merge \
  -p '{"status":{"phase":"Bogus"}}'       # must be REJECTED

kubectl -n layernetes delete llagent qa-sample
```

Note: the operator will briefly reconcile `qa-sample` (phase `Pending`,
no image → no-op) and its finalizer removes a namespace that never
existed — deletion should still complete promptly.

## 5. ll-api contract

```sh
API=http://api.192.168.64.200.sslip.io
curl -s $API/healthz                                          # {"ok":true}

# login → bearer token
TOKEN=$(curl -s -X POST $API/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"layernetes-admin","password":"layernetes-local-dev"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -s -H "Authorization: Bearer $TOKEN" $API/v1/me           # username + age_public_key

# negative: builds callback rejects a bad CI token
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  $API/v1/agents/layernetes-admin-hello-agent/builds \
  -H 'Authorization: Bearer wrong' -H 'Content-Type: application/json' \
  -d '{"sha":"abc1234","image":"x"}'                           # 401

# negative: no auth
curl -s -o /dev/null -w '%{http_code}\n' $API/v1/me            # 401
```

## 6. The end-to-end loop (the acceptance test)

This is the README's Quickstart against your local control plane — the
single most important QA item. Use a scratch directory:

```sh
export LLNATE_API_URL=http://api.192.168.64.200.sslip.io
export LLNATE_USERNAME=layernetes-admin LLNATE_PASSWORD=layernetes-local-dev
LLNATE=/path/to/layernetes/llnate/.venv/bin/llnate   # or pip install -e llnate

$LLNATE init qa-agent && cd qa-agent
$LLNATE login          # prints age public key + provisioned repo
$LLNATE keys OPENAI_API_KEY=sk-dummy-qa
git add keys.env .sops.yaml && git commit -m "keys"   # llnate never auto-commits your keys
$LLNATE push
```

**Pass:** `push` streams `phase: Pending → Deploying → Ready` (first build
takes a few minutes: the runner pulls the CI image and the base image once,
then caches) and prints three URLs. Verify each surface of the runtime
contract:

```sh
URL=$($LLNATE status | grep HTTP | awk '{print $2}')
curl -s $URL/healthz                       # {"ok":true,"agent":"llagent"}
curl -s -o /dev/null -w '%{http_code}\n' $URL/docs    # 200

# real MCP handshake (expect a jsonrpc result with serverInfo)
curl -s -X POST $URL/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"qa","version":"0"}}}'
```

### 6b. The secrets contract (in-memory decrypt)

```sh
NS=agent-layernetes-admin-qa-agent
kubectl -n $NS logs deploy/agent | head -1
#   "entrypoint: decrypting /app/keys.env with sops exec-env ..."

kubectl -n $NS exec deploy/agent -- sh -c 'head -c 60 /app/keys.env; echo'
#   still ENCRYPTED on disk (ENC[AES256_GCM,...)

kubectl -n $NS exec deploy/agent -- sh -c 'env | grep -c OPENAI'   # 0 !
# a fresh exec shell must NOT see the credential; only the server process has it:
kubectl -n $NS exec deploy/agent -- sh -c \
  'for p in $(ls /proc | grep -E "^[0-9]+$"); do
     grep -q uvicorn /proc/$p/cmdline 2>/dev/null &&
     tr "\0" "\n" < /proc/$p/environ | grep -c "^OPENAI_API_KEY=" && break
   done'                                                            # 1
```

### 6c. Revision semantics (MVP: latest-only)

```sh
OLD=$($LLNATE status | grep HTTP | awk '{print $2}')
git commit --allow-empty -m "second revision" && $LLNATE push
NEW=$($LLNATE status | grep HTTP | awk '{print $2}')
[ "$OLD" != "$NEW" ] && echo "new sha hostname: OK"
curl -s -o /dev/null -w '%{http_code}\n' $NEW/docs   # 200 — new agent up
curl -s -o /dev/null -w '%{http_code}\n' $OLD/docs   # 404 — old sha stopped resolving
```

Check the old sha on `/docs` (or `/`), **not** `/healthz`: `/healthz` is a
reserved path on the ingress-nginx controller that returns 200 for *any*
Host header, so it would mask a properly-removed ingress. `/docs` falls
through to nginx's default backend (404) once the old ingress is gone.

Note: `$LLNATE push` waits for the platform to report the sha it just
pushed, so the URLs it prints are always the new revision's (it won't exit
early against a stale Ready). The standalone `$LLNATE status` command,
however, just reports the CR's current state, which only advances to the new
revision once CI reports its build — a few seconds behind the git push. If
`status` still shows the old sha right after a push, give it a moment, or
read the live sha with
`kubectl -n layernetes get llagent <cr> -o jsonpath='{.spec.sha}'`.

### 6d. Teardown

```sh
$LLNATE delete --yes
kubectl get ns | grep qa-agent            # gone (may take ~30s)
curl -s -o /dev/null -w '%{http_code}\n' -u layernetes-admin:layernetes-local-dev \
  http://gitea.192.168.64.200.sslip.io/api/v1/repos/layernetes-admin/qa-agent   # 404
kubectl -n layernetes get llagents        # qa-agent CR gone
```

## 7. Watching a build when something goes wrong

```sh
# CI runs and their state
curl -s -u layernetes-admin:layernetes-local-dev \
  'http://gitea.192.168.64.200.sslip.io/api/v1/repos/layernetes-admin/<repo>/actions/tasks' \
  | python3 -m json.tool | grep -E '"id"|"status"'

# a specific job's log (job id from above)
curl -s -u layernetes-admin:layernetes-local-dev \
  'http://gitea.192.168.64.200.sslip.io/api/v1/repos/layernetes-admin/<repo>/actions/jobs/<id>/logs' | tail -50

kubectl -n layernetes logs deploy/ll-operator --tail=20     # reconcile errors
kubectl -n layernetes logs deploy/ll-api --tail=20          # provisioning/API errors
kubectl -n agent-<cr-name> get pods                         # agent pod state
```

The README's Troubleshooting section covers the known failure signatures
(registry trust, runner idle, sslip DNS, kiac bulk-transfer stalls).

## QA checklist (tl;dr)

- [ ] 4 test suites green (27 / 38 / 11 / 28)
- [ ] `helm lint` clean; install brings up 4 Running deployments
- [ ] Gitea API + registry `/v2/` respond through the ingress; runner "declare successfully"
- [ ] CRD: sample applies, status patches, bogus phase rejected
- [ ] ll-api: healthz, login→me round-trip, 401s on bad/absent tokens
- [ ] E2E: `init → login → keys → push` reaches Ready and prints URLs
- [ ] Agent: /healthz ok, /docs 200, MCP initialize succeeds
- [ ] Secrets: keys.env encrypted on disk, credential only in server process
- [ ] New sha replaces old hostname (old 404s)
- [ ] `llnate delete` removes namespace, repo, and CR
