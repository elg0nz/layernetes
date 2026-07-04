"""Thin synchronous Gitea REST client (httpx).

All methods raise GiteaError on non-success responses; main.py maps those to
HTTP errors (Gitea 4xx -> 400, everything else -> 502). Repo Actions
secrets/variables are written with the caller's own token first, falling back
to the platform admin credentials on 403 (user tokens may lack that scope).
"""

import httpx

TOKEN_SCOPES = ["write:repository", "write:package", "write:user"]


class GiteaError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(f"gitea returned {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class GiteaClient:
    def __init__(
        self,
        base_url: str,
        admin_username: str | None = None,
        admin_password: str | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._admin = (
            (admin_username, admin_password) if admin_username and admin_password else None
        )
        self._client = httpx.Client(base_url=f"{self.base_url}/api/v1", timeout=timeout)

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        basic: tuple[str, str] | None = None,
        ok: tuple[int, ...] = (200, 201, 204),
        **kwargs,
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"token {token}"
        try:
            resp = self._client.request(method, path, headers=headers, auth=basic, **kwargs)
        except httpx.HTTPError as exc:
            raise GiteaError(503, f"gitea unreachable: {exc}") from exc
        if resp.status_code not in ok:
            try:
                detail = resp.json().get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise GiteaError(resp.status_code, detail or resp.reason_phrase)
        return resp

    def _with_admin_fallback(self, method: str, path: str, token: str, **kwargs) -> httpx.Response:
        try:
            return self._request(method, path, token=token, **kwargs)
        except GiteaError as exc:
            if exc.status_code == 403 and self._admin:
                return self._request(method, path, basic=self._admin, **kwargs)
            raise

    # -- auth / identity -----------------------------------------------------

    def create_user_token(self, username: str, password: str, name: str) -> str:
        resp = self._request(
            "POST",
            f"/users/{username}/tokens",
            basic=(username, password),
            json={"name": name, "scopes": TOKEN_SCOPES},
            ok=(201,),
        )
        return resp.json()["sha1"]

    def get_user(self, token: str) -> dict:
        return self._request("GET", "/user", token=token, ok=(200,)).json()

    # -- repos ---------------------------------------------------------------

    def create_repo(self, token: str, name: str) -> dict:
        """Create a repo for the token's user. Raises GiteaError(409) if it exists."""
        return self._request(
            "POST",
            "/user/repos",
            token=token,
            json={"name": name, "auto_init": False, "private": False},
            ok=(201,),
        ).json()

    def delete_repo(self, token: str, owner: str, name: str) -> None:
        self._request("DELETE", f"/repos/{owner}/{name}", token=token, ok=(204, 404))

    # -- Actions secrets / variables ------------------------------------------

    def set_actions_secret(self, token: str, owner: str, repo: str, name: str, value: str) -> None:
        self._with_admin_fallback(
            "PUT",
            f"/repos/{owner}/{repo}/actions/secrets/{name}",
            token,
            json={"data": value},
            ok=(201, 204),
        )

    def set_actions_variable(self, token: str, owner: str, repo: str, name: str, value: str) -> None:
        path = f"/repos/{owner}/{repo}/actions/variables/{name}"
        try:
            self._with_admin_fallback("POST", path, token, json={"value": value}, ok=(201, 204))
        except GiteaError as exc:
            if exc.status_code in (400, 409):  # already exists -> update in place
                self._with_admin_fallback("PUT", path, token, json={"value": value}, ok=(200, 201, 204))
            else:
                raise
