"""Thin Kubernetes client helpers for ll-operator.

Everything writes via server-side apply (SSA): one PATCH with
`application/apply-patch+yaml` both creates and updates, and because our
field manager owns spec.rules on the Ingress, a sha change *replaces* the
host list instead of merging into it — exactly the MVP revision semantics.

All functions are module-level and take plain dicts so main.py stays thin
and tests can monkeypatch/mock them without a cluster.
"""

from __future__ import annotations

from kubernetes import client, config
from kubernetes.client.rest import ApiException

FIELD_MANAGER = "ll-operator"

GROUP = "layernetes.learninglayer.ai"
VERSION = "v1alpha1"
PLURAL = "llagents"

_apis: dict = {}


def load_config() -> None:
    """In-cluster when deployed, kubeconfig when run locally."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _api(cls):
    if cls not in _apis:
        _apis[cls] = cls()
    return _apis[cls]


def core() -> client.CoreV1Api:
    return _api(client.CoreV1Api)


def apps() -> client.AppsV1Api:
    return _api(client.AppsV1Api)


def networking() -> client.NetworkingV1Api:
    return _api(client.NetworkingV1Api)


def custom_objects() -> client.CustomObjectsApi:
    return _api(client.CustomObjectsApi)


# --- server-side apply -------------------------------------------------------
#
# The generated patch_* wrappers reject the `_content_type` kwarg on some
# client versions (33.x raises "unexpected keyword argument"), so SSA goes
# through the REST layer directly: one PATCH with apply-patch+yaml against
# the named resource URL, which both creates and updates.

def _ssa(path: str, body: dict) -> None:
    core().api_client.call_api(
        path,
        "PATCH",
        header_params={
            "Content-Type": "application/apply-patch+yaml",
            "Accept": "application/json",
        },
        query_params=[("fieldManager", FIELD_MANAGER), ("force", "true")],
        body=body,
        auth_settings=["BearerToken"],
        response_type="object",
    )


def apply_namespace(body: dict) -> None:
    _ssa(f"/api/v1/namespaces/{body['metadata']['name']}", body)


def apply_secret(body: dict) -> None:
    meta = body["metadata"]
    _ssa(f"/api/v1/namespaces/{meta['namespace']}/secrets/{meta['name']}", body)


def apply_deployment(body: dict) -> None:
    meta = body["metadata"]
    _ssa(f"/apis/apps/v1/namespaces/{meta['namespace']}/deployments/{meta['name']}", body)


def apply_service(body: dict) -> None:
    meta = body["metadata"]
    _ssa(f"/api/v1/namespaces/{meta['namespace']}/services/{meta['name']}", body)


def apply_ingress(body: dict) -> None:
    meta = body["metadata"]
    _ssa(
        f"/apis/networking.k8s.io/v1/namespaces/{meta['namespace']}/ingresses/{meta['name']}",
        body,
    )


def apply_network_policy(body: dict) -> None:
    meta = body["metadata"]
    _ssa(
        f"/apis/networking.k8s.io/v1/namespaces/{meta['namespace']}/networkpolicies/{meta['name']}",
        body,
    )


# --- reads -------------------------------------------------------------------

def get_secret_data(name: str, namespace: str) -> dict | None:
    """Base64 data of a Secret, or None if it does not exist."""
    try:
        secret = core().read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    return dict(secret.data or {})


def get_deployment_status(name: str, namespace: str) -> dict | None:
    """Observed Deployment status as a plain dict, or None if absent."""
    try:
        dep = apps().read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    status = dep.status
    conditions = [
        {
            "type": c.type,
            "status": c.status,
            "reason": c.reason,
            "message": c.message,
        }
        for c in (status.conditions or [])
    ]
    return {
        "observedGeneration": status.observed_generation,
        "replicas": status.replicas,
        "updatedReplicas": status.updated_replicas,
        "readyReplicas": status.ready_replicas,
        "availableReplicas": status.available_replicas,
        "conditions": conditions,
    }


# --- deletes -----------------------------------------------------------------

def delete_namespace(name: str) -> None:
    """Delete the agent namespace; cascades everything inside it."""
    try:
        core().delete_namespace(name=name)
    except ApiException as exc:
        if exc.status != 404:
            raise
