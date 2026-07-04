# llagent-base

The Docker base image every LLAgent runs on. It bundles Python 3.12, a pinned
CrewAI, the FastMCP/FastAPI wrapper (`server.py`), `sops` + `age`, and the
secret-decrypting entrypoint. User projects built by `llnate init` just layer
their code on top:

```dockerfile
FROM llagent-base:dev
COPY . /app          # must include crew.py; keys.env if you have secrets
```

## Runtime contract

(Frozen in the top-level README; `ll-operator` depends on it.)

- **Port `8000`**, plain HTTP.
- **`GET /healthz`** — liveness/readiness. Returns `200 {"ok": true}` only
  when the server is up **and** the user's crew imported successfully.
  If `crew.py` is missing or fails to import, the server still starts and
  `/healthz` returns `503 {"ok": false, "error": "<traceback>"}` — the pod is
  alive (the operator and the developer can read the error) but never goes
  `Ready`.
- **`POST /kickoff`** — REST: `{"inputs": {...}}` → runs
  `crew.kickoff(inputs=...)` in a threadpool → `{"result": "<str(result)>"}`.
  `503` if the crew is unavailable.
- **`/mcp`** — FastMCP server (streamable HTTP transport), named after the
  agent (`LLAGENT_NAME` env var), exposing a `kickoff` tool with the same
  behavior.
- **`/docs` + `/openapi.json`** — the FastAPI surface.

**User code convention:** the project provides `/app/crew.py` exposing a
module-level CrewAI `crew` object. `server.py` imports it lazily with `/app`
first on `sys.path`, so a broken crew never prevents the HTTP app (and
`/healthz`) from coming up.

## How the entrypoint decrypts secrets

`entrypoint.sh` sets `SOPS_AGE_KEY_FILE` (default
`/var/run/secrets/llnate/age.key`, where `ll-operator` mounts the age private
key), then:

- If **both** `/app/keys.env` and the age key file exist:
  `exec sops exec-env /app/keys.env "uvicorn server:app --host 0.0.0.0 --port 8000"`
  — sops decrypts `keys.env` and injects the values into the server process's
  environment. **Plaintext is never written to disk.**
- Otherwise (local dev, no secrets): it execs uvicorn directly, logging which
  path was taken to stderr.

## Layout inside the image

| Path | Contents |
| --- | --- |
| `/opt/llagent/server.py` | the wrapper (`server:app`) |
| `/opt/llagent/entrypoint.sh` | the entrypoint |
| `/app` | `WORKDIR`; the user's project (`crew.py`, `keys.env`) |

`PYTHONPATH=/opt/llagent:/app`, so `uvicorn server:app` resolves the wrapper
from `/opt/llagent` while `import crew` resolves the user's code (`server.py`
additionally puts `/app` at the front of `sys.path` before importing `crew`).
Runs as non-root user `llagent` (uid 10001).

## Build

```sh
docker build -t llagent-base:dev .
# multi-arch: docker buildx build --platform linux/amd64,linux/arm64 -t llagent-base:dev .
```

Pinned versions: crewai 1.15.1, fastmcp 3.4.2, fastapi 0.139.0,
uvicorn 0.49.0, sops v3.9.4, age v1.2.1 (sops/age binaries are
checksum-verified per arch at build time).

## Tests

The tests stub the crew (`sys.modules["crew"]`) so crewai itself isn't needed:

```sh
python3 -m venv .venv && .venv/bin/pip install fastmcp fastapi uvicorn pytest httpx
.venv/bin/python -m pytest
```
