import httpx
import pytest

from app.gitea import GiteaClient, GiteaError
from tests.conftest import GITEA_URL


@pytest.fixture
def gitea():
    return GiteaClient(GITEA_URL, "gitea-admin", "admin-pw")


def test_actions_secret_admin_fallback(gitea, gitea_mock):
    """403 with the user token retries with admin basic auth."""
    path = "/api/v1/repos/gonz/hello-agent/actions/secrets/LL_API_TOKEN"
    route = gitea_mock.put(path)
    route.side_effect = [
        httpx.Response(403, json={"message": "scope"}),
        httpx.Response(201),
    ]
    gitea.set_actions_secret("user-tok", "gonz", "hello-agent", "LL_API_TOKEN", "value")
    assert route.call_count == 2
    assert route.calls.last.request.headers["Authorization"].startswith("Basic ")


def test_actions_variable_update_on_conflict(gitea, gitea_mock):
    """POST 409 (variable exists) falls back to PUT."""
    path = "/api/v1/repos/gonz/hello-agent/actions/variables/REGISTRY"
    gitea_mock.post(path).respond(409, json={"message": "exists"})
    put_route = gitea_mock.put(path).respond(204)
    gitea.set_actions_variable("user-tok", "gonz", "hello-agent", "REGISTRY", "reg:8080")
    assert put_route.called


def test_error_carries_gitea_message(gitea, gitea_mock):
    gitea_mock.get("/api/v1/user").respond(500, json={"message": "boom"})
    with pytest.raises(GiteaError) as excinfo:
        gitea.get_user("tok")
    assert excinfo.value.status_code == 500
    assert "boom" in excinfo.value.detail
