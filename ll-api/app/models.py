"""Pydantic schemas mirroring the README contract."""

from pydantic import BaseModel, Field

# Lowercase DNS-label-ish: the agent name ends up in Secret and CR names.
AGENT_NAME_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


class MeResponse(BaseModel):
    username: str
    age_public_key: str = ""


class AgentCreateRequest(BaseModel):
    name: str = Field(pattern=AGENT_NAME_PATTERN)


class AgentCreateResponse(BaseModel):
    name: str
    repo: str
    clone_url: str
    age_public_key: str


class BuildRequest(BaseModel):
    sha: str
    image: str


class AgentStatusResponse(BaseModel):
    phase: str = "Pending"
    url: str = ""
    message: str = ""
    # The deployed revision's short SHA (from LLAgent.spec.sha). Empty until
    # CI reports the first build. `llnate push` uses this to tell its own
    # revision apart from a stale status left by a previous one.
    sha: str = ""
