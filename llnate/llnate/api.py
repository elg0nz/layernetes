"""HTTP client for the ll-api control plane.

The endpoint shapes are frozen by the repository README ("ll-api REST API"):

- ``POST /v1/auth/login``  {"username", "password"} -> {"token", "username"}
- ``GET  /v1/me``          (Bearer) -> {"username", "age_public_key"}
- ``POST /v1/agents``      (Bearer) {"name"} -> 201
      {"name", "repo", "clone_url", "age_public_key"}
- ``GET  /v1/agents/{name}/status`` (Bearer) ->
      {"phase": "Pending|Deploying|Ready|Failed", "url", "message"}
- ``DELETE /v1/agents/{name}`` (Bearer)
"""

from __future__ import annotations

import httpx


class ApiError(Exception):
    """A failed ll-api request, with a human-readable message."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message") or body.get("error")
            if detail:
                return str(detail)
    except ValueError:
        pass
    text = response.text.strip()
    return text or f"HTTP {response.status_code}"


class Client:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"cannot reach ll-api at {self._http.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise ApiError(
                f"{method} {path} failed ({response.status_code}): "
                f"{_error_message(response)}",
                status_code=response.status_code,
            )
        return response

    # -- endpoints ---------------------------------------------------------

    def login(self, username: str, password: str) -> dict:
        response = self._request(
            "POST", "/v1/auth/login", json={"username": username, "password": password}
        )
        return response.json()

    def me(self) -> dict:
        return self._request("GET", "/v1/me").json()

    def create_agent(self, name: str) -> dict:
        return self._request("POST", "/v1/agents", json={"name": name}).json()

    def agent_status(self, name: str) -> dict:
        return self._request("GET", f"/v1/agents/{name}/status").json()

    def delete_agent(self, name: str) -> None:
        self._request("DELETE", f"/v1/agents/{name}")
