import base64
from unittest import mock

import pytest
import respx
from fastapi.testclient import TestClient
from kubernetes import client as k8s
from kubernetes.client.exceptions import ApiException

from app.kube import Kube
from app.main import Settings, create_app

GITEA_URL = "http://gitea.layernetes.svc:3000"
GITEA_EXTERNAL_URL = "http://gitea.127.0.0.1.sslip.io:8080"


def make_fake_core(store: dict) -> mock.MagicMock:
    """CoreV1Api mock backed by an in-memory {name: V1Secret} store."""
    core = mock.MagicMock(spec=k8s.CoreV1Api)

    def read(name, namespace):
        if name not in store:
            raise ApiException(status=404)
        return store[name]

    def create(namespace, body):
        name = body.metadata.name
        if name in store:
            raise ApiException(status=409)
        data = {
            k: base64.b64encode(v.encode()).decode() for k, v in (body.string_data or {}).items()
        }
        store[name] = k8s.V1Secret(metadata=body.metadata, data=data)
        return store[name]

    def delete(name, namespace):
        if name not in store:
            raise ApiException(status=404)
        del store[name]

    core.read_namespaced_secret.side_effect = read
    core.create_namespaced_secret.side_effect = create
    core.delete_namespaced_secret.side_effect = delete
    return core


def make_fake_custom(store: dict) -> mock.MagicMock:
    """CustomObjectsApi mock backed by an in-memory {name: dict} store."""
    custom = mock.MagicMock(spec=k8s.CustomObjectsApi)

    def get(group, version, namespace, plural, name):
        if name not in store:
            raise ApiException(status=404)
        return store[name]

    def create(group, version, namespace, plural, body):
        name = body["metadata"]["name"]
        if name in store:
            raise ApiException(status=409)
        store[name] = body
        return body

    def patch(group, version, namespace, plural, name, body):
        if name not in store:
            raise ApiException(status=404)
        store[name].setdefault("spec", {}).update(body.get("spec", {}))
        return store[name]

    def delete(group, version, namespace, plural, name):
        if name not in store:
            raise ApiException(status=404)
        del store[name]

    custom.get_namespaced_custom_object.side_effect = get
    custom.create_namespaced_custom_object.side_effect = create
    custom.patch_namespaced_custom_object.side_effect = patch
    custom.delete_namespaced_custom_object.side_effect = delete
    return custom


@pytest.fixture
def secret_store() -> dict:
    return {}


@pytest.fixture
def cr_store() -> dict:
    return {}


@pytest.fixture
def kube(secret_store, cr_store) -> Kube:
    return Kube(
        "layernetes", core=make_fake_core(secret_store), custom=make_fake_custom(cr_store)
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gitea_url=GITEA_URL,
        gitea_external_url=GITEA_EXTERNAL_URL,
        gitea_admin_username="gitea-admin",
        gitea_admin_password="admin-pw",
        platform_namespace="layernetes",
        api_external_url="http://api.127.0.0.1.sslip.io:8080",
        agents_domain="agents.127.0.0.1.sslip.io",
        agent_url_scheme="http",
        agent_url_port_suffix=":8080",
        log_level="info",
    )


@pytest.fixture
def client(settings, kube) -> TestClient:
    app = create_app(settings=settings, kube=kube)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def gitea_mock():
    with respx.mock(base_url=GITEA_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def as_user(gitea_mock):
    """Mock Gitea identity resolution; returns (headers, username)."""

    def _login(username="gonz", token="user-token-123", is_admin=False):
        gitea_mock.get("/api/v1/user").respond(
            200, json={"id": 1, "login": username, "is_admin": is_admin}
        )
        return {"Authorization": f"Bearer {token}"}, username

    return _login
