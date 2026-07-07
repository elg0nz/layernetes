"""ll-api: the Layernetes control-plane FastAPI service.

Auth note (MVP): the README describes ``POST /v1/auth/login`` as an OAuth
handshake against Gitea. The accepted MVP simplification implemented here is
password login: the endpoint takes ``{"username", "password"}``, mints a
Gitea personal access token via Gitea's basic-auth token API, and returns it.
That Gitea token *is* the bearer token for every user-auth endpoint (identity
is resolved per-request via ``GET {GITEA_URL}/api/v1/user``), so a real OAuth
flow can later replace how the token is obtained without changing the
endpoint shape or anything downstream.

Naming: provisioning returns the cluster-wide agent name ``<username>-<name>``
and that is what CI must use on ``/v1/agents/{name}/builds``. User-auth agent
endpoints accept either the full name or the short repo name (which gets
prefixed with the caller's username).
"""

import hmac
import logging
import os
import secrets as pysecrets
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .auth import AuthedUser, bearer_token, require_user
from .gitea import GiteaClient, GiteaError
from .kube import Kube
from .models import (
    AgentCreateRequest,
    AgentCreateResponse,
    AgentStatusResponse,
    BuildRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
)

logger = logging.getLogger("ll-api")


@dataclass
class Settings:
    gitea_url: str
    gitea_external_url: str
    gitea_admin_username: str
    gitea_admin_password: str
    platform_namespace: str
    api_external_url: str
    agents_domain: str
    agent_url_scheme: str
    agent_url_port_suffix: str
    log_level: str
    llagent_base_image: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        gitea_url = env.get("GITEA_URL", "http://localhost:3000")
        return cls(
            gitea_url=gitea_url,
            gitea_external_url=env.get("GITEA_EXTERNAL_URL", gitea_url),
            gitea_admin_username=env.get("GITEA_ADMIN_USERNAME", ""),
            gitea_admin_password=env.get("GITEA_ADMIN_PASSWORD", ""),
            platform_namespace=env.get("PLATFORM_NAMESPACE", "layernetes"),
            api_external_url=env.get("API_EXTERNAL_URL", "http://localhost:8000"),
            agents_domain=env.get("AGENTS_DOMAIN", "agents.127.0.0.1.sslip.io"),
            agent_url_scheme=env.get("AGENT_URL_SCHEME", "http"),
            agent_url_port_suffix=env.get("AGENT_URL_PORT_SUFFIX", ""),
            log_level=env.get("LOG_LEVEL", "info"),
            llagent_base_image=env.get("LLAGENT_BASE_IMAGE", ""),
        )

    @property
    def registry_host(self) -> str:
        """Registry host[:port] agents push/pull against, from GITEA_EXTERNAL_URL."""
        return urlparse(self.gitea_external_url).netloc

    @property
    def internal_api_url(self) -> str:
        return f"http://ll-api.{self.platform_namespace}.svc.cluster.local:8000"


def _ci_secret_name(agent_name: str) -> str:
    # agent_name is the CR name <username>-<name>, so this matches the
    # ll-ci-token-<username>-<name> convention.
    return f"ll-ci-token-{agent_name}"


def create_app(settings: Settings | None = None, kube: Kube | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(title="ll-api", version="0.1.0")
    app.state.settings = settings
    app.state.gitea = GiteaClient(
        settings.gitea_url,
        settings.gitea_admin_username or None,
        settings.gitea_admin_password or None,
    )
    app.state.kube = kube  # created lazily so import/healthz never needs a cluster

    def get_kube(request: Request) -> Kube:
        if request.app.state.kube is None:
            request.app.state.kube = Kube(settings.platform_namespace)
        return request.app.state.kube

    def resolve_owned_agent(kube: Kube, user: AuthedUser, name: str) -> dict:
        """Find the caller's LLAgent by full CR name or short repo name."""
        candidates = dict.fromkeys([name, f"{user.username}-{name}"])
        for candidate in candidates:
            cr = kube.get_llagent(candidate)
            if cr is not None and cr.get("spec", {}).get("owner") == user.username:
                return cr
        raise HTTPException(status_code=404, detail="agent not found")

    @app.exception_handler(GiteaError)
    def gitea_error_handler(request: Request, exc: GiteaError) -> JSONResponse:
        status = 400 if 400 <= exc.status_code < 500 else 502
        return JSONResponse(status_code=status, content={"detail": f"gitea: {exc.detail}"})

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.post("/v1/auth/login", response_model=LoginResponse)
    def login(body: LoginRequest) -> LoginResponse:
        try:
            token = app.state.gitea.create_user_token(
                body.username, body.password, f"llnate-{pysecrets.token_hex(4)}"
            )
        except GiteaError as exc:
            if exc.status_code in (401, 403):
                raise HTTPException(status_code=401, detail="invalid username or password") from exc
            raise
        return LoginResponse(token=token, username=body.username)

    @app.get("/v1/me", response_model=MeResponse)
    def me(request: Request, user: AuthedUser = Depends(require_user)) -> MeResponse:
        public_key = get_kube(request).get_age_public_key(user.username)
        return MeResponse(username=user.username, age_public_key=public_key or "")

    @app.post("/v1/agents", status_code=201, response_model=AgentCreateResponse)
    def create_agent(
        request: Request, body: AgentCreateRequest, user: AuthedUser = Depends(require_user)
    ) -> AgentCreateResponse:
        gitea: GiteaClient = app.state.gitea
        kube = get_kube(request)
        repo = f"{user.username}/{body.name}"
        cr_name = f"{user.username}-{body.name}"

        try:
            gitea.create_repo(user.token, body.name)
        except GiteaError as exc:
            if exc.status_code != 409:  # already exists -> idempotent, continue
                raise

        age_public_key = kube.ensure_age_key(user.username)

        ci_secret = kube.get_secret(_ci_secret_name(cr_name))
        ci_token = Kube.secret_value(ci_secret, "token") if ci_secret else None
        if not ci_token:
            ci_token = pysecrets.token_urlsafe(32)
            kube.create_secret(_ci_secret_name(cr_name), {"token": ci_token})

        gitea.set_actions_secret(user.token, user.username, body.name, "LL_API_TOKEN", ci_token)
        gitea.set_actions_variable(
            user.token, user.username, body.name, "LL_API_URL", settings.internal_api_url
        )
        gitea.set_actions_variable(
            user.token, user.username, body.name, "REGISTRY", settings.registry_host
        )
        if settings.llagent_base_image:
            gitea.set_actions_variable(
                user.token, user.username, body.name, "BASE_IMAGE", settings.llagent_base_image
            )
        # Registry credentials for CI's `docker login`: the caller's own PAT
        # (minted at login with write:package scope). The random LL_API_TOKEN
        # is not a Gitea credential, so the workflow's fallback would fail.
        gitea.set_actions_secret(user.token, user.username, body.name, "REGISTRY_USER", user.username)
        gitea.set_actions_secret(user.token, user.username, body.name, "REGISTRY_PASSWORD", user.token)

        kube.create_llagent(
            cr_name,
            {"owner": user.username, "repo": repo, "keySecretRef": f"age-key-{user.username}"},
        )
        logger.info("provisioned agent %s (repo %s)", cr_name, repo)
        return AgentCreateResponse(
            name=cr_name,
            repo=repo,
            clone_url=f"{settings.gitea_external_url.rstrip('/')}/{repo}.git",
            age_public_key=age_public_key,
        )

    @app.post("/v1/agents/{name}/builds")
    def report_build(
        name: str, body: BuildRequest, request: Request, token: str = Depends(bearer_token)
    ) -> dict:
        kube = get_kube(request)
        secret = kube.get_secret(_ci_secret_name(name))
        expected = Kube.secret_value(secret, "token") if secret else None
        if not expected or not hmac.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="invalid CI token")
        if kube.get_llagent(name) is None:
            raise HTTPException(status_code=404, detail="agent not found")
        kube.patch_llagent_spec(name, {"image": body.image, "sha": body.sha})
        logger.info("build reported for %s: sha=%s", name, body.sha)
        return {"name": name, "sha": body.sha, "image": body.image}

    @app.get("/v1/agents/{name}/status", response_model=AgentStatusResponse)
    def agent_status(
        name: str, request: Request, user: AuthedUser = Depends(require_user)
    ) -> AgentStatusResponse:
        cr = resolve_owned_agent(get_kube(request), user, name)
        status = cr.get("status") or {}
        spec = cr.get("spec") or {}
        return AgentStatusResponse(
            phase=status.get("phase") or "Pending",
            url=status.get("url") or "",
            message=status.get("message") or "",
            sha=spec.get("sha") or "",
        )

    @app.delete("/v1/agents/{name}", status_code=204)
    def delete_agent(
        name: str, request: Request, user: AuthedUser = Depends(require_user)
    ) -> Response:
        kube = get_kube(request)
        cr = resolve_owned_agent(kube, user, name)
        cr_name = cr["metadata"]["name"]
        owner, _, repo_name = cr["spec"]["repo"].partition("/")

        # The operator's finalizer tears down the agent namespace.
        kube.delete_llagent(cr_name)
        app.state.gitea.delete_repo(user.token, owner, repo_name)
        kube.delete_secret(_ci_secret_name(cr_name))
        # The age-key Secret is per-user (shared across agents) and is kept.
        logger.info("deleted agent %s", cr_name)
        return Response(status_code=204)

    return app


app = create_app()
