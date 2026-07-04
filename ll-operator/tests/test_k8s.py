"""k8s helper tests: server-side apply plumbing and 404 tolerance,
with the kubernetes client fully mocked (no cluster required)."""

from unittest import mock

import pytest
from kubernetes.client.rest import ApiException

import k8s


@pytest.fixture(autouse=True)
def clear_api_cache():
    k8s._apis.clear()
    yield
    k8s._apis.clear()


def test_apply_ingress_uses_server_side_apply(monkeypatch):
    api = mock.Mock()
    monkeypatch.setattr(k8s, "core", lambda: api)
    body = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {"name": "agent", "namespace": "agent-x"},
    }
    k8s.apply_ingress(body)
    call = api.api_client.call_api.call_args
    assert call.args == (
        "/apis/networking.k8s.io/v1/namespaces/agent-x/ingresses/agent",
        "PATCH",
    )
    assert call.kwargs["header_params"]["Content-Type"] == "application/apply-patch+yaml"
    assert ("fieldManager", "ll-operator") in call.kwargs["query_params"]
    assert ("force", "true") in call.kwargs["query_params"]
    assert call.kwargs["body"] is body


def test_apply_namespace_uses_metadata_name(monkeypatch):
    api = mock.Mock()
    monkeypatch.setattr(k8s, "core", lambda: api)
    body = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "agent-x"}}
    k8s.apply_namespace(body)
    call = api.api_client.call_api.call_args
    assert call.args == ("/api/v1/namespaces/agent-x", "PATCH")
    assert ("force", "true") in call.kwargs["query_params"]


def test_get_secret_data_returns_none_on_404(monkeypatch):
    api = mock.Mock()
    api.read_namespaced_secret.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s, "core", lambda: api)
    assert k8s.get_secret_data("age-key-gonz", "layernetes") is None


def test_get_secret_data_reraises_other_errors(monkeypatch):
    api = mock.Mock()
    api.read_namespaced_secret.side_effect = ApiException(status=403)
    monkeypatch.setattr(k8s, "core", lambda: api)
    with pytest.raises(ApiException):
        k8s.get_secret_data("age-key-gonz", "layernetes")


def test_get_secret_data_returns_data_dict(monkeypatch):
    api = mock.Mock()
    api.read_namespaced_secret.return_value = mock.Mock(data={"age.key": "QUdF"})
    monkeypatch.setattr(k8s, "core", lambda: api)
    assert k8s.get_secret_data("age-key-gonz", "layernetes") == {"age.key": "QUdF"}


def test_get_deployment_status_none_on_404(monkeypatch):
    api = mock.Mock()
    api.read_namespaced_deployment.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s, "apps", lambda: api)
    assert k8s.get_deployment_status("agent", "agent-x") is None


def test_get_deployment_status_extracts_plain_dict(monkeypatch):
    condition = mock.Mock(status="True", reason="MinimumReplicasAvailable", message="ok")
    condition.type = "Available"  # `type` can't be set via Mock kwargs
    status = mock.Mock(
        observed_generation=2,
        replicas=1,
        updated_replicas=1,
        ready_replicas=1,
        available_replicas=1,
        conditions=[condition],
    )
    api = mock.Mock()
    api.read_namespaced_deployment.return_value = mock.Mock(status=status)
    monkeypatch.setattr(k8s, "apps", lambda: api)
    result = k8s.get_deployment_status("agent", "agent-x")
    assert result["readyReplicas"] == 1
    assert result["conditions"] == [
        {"type": "Available", "status": "True", "reason": "MinimumReplicasAvailable", "message": "ok"}
    ]


def test_delete_namespace_tolerates_404(monkeypatch):
    api = mock.Mock()
    api.delete_namespace.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s, "core", lambda: api)
    k8s.delete_namespace("agent-x")  # must not raise
