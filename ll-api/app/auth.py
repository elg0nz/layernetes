"""Auth dependencies.

User auth: the bearer token is a Gitea personal access token (issued by
POST /v1/auth/login); identity is resolved per-request via Gitea's
GET /api/v1/user. CI auth (builds callback) is handled in the endpoint
itself, since it needs the agent name from the path.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .gitea import GiteaError

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthedUser:
    username: str
    token: str


def bearer_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return credentials.credentials


def require_user(request: Request, token: str = Depends(bearer_token)) -> AuthedUser:
    try:
        user = request.app.state.gitea.get_user(token)
    except GiteaError as exc:
        if exc.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid token") from exc
        raise HTTPException(status_code=502, detail=f"gitea: {exc.detail}") from exc
    return AuthedUser(username=user["login"], token=token)
