"""Pure builders for every Kubernetes object ll-operator manages.

No I/O in this module: every function takes plain values and returns plain
dicts (server-side-apply-ready manifests) or plain status dicts. This is the
part of the operator that encodes the frozen MVP contract (README:
"The LLAgent custom resource" + "Agent runtime contract"), and it is what the
unit tests pin down.
"""

from __future__ import annotations

import posixpath

GROUP = "layernetes.learninglayer.ai"
AGENT_LABEL = f"{GROUP}/agent"
PART_OF_LABEL = "app.kubernetes.io/part-of"
PART_OF_VALUE = "layernetes"

# Contract constants (README "Agent runtime contract").
AGENT_PORT = 8000
HEALTH_PATH = "/healthz"
AGE_KEY_FILENAME = "age.key"
DEFAULT_AGE_KEY_MOUNT_PATH = "/var/run/secrets/llnate/age.key"

# All child resources in the agent namespace share this fixed name; the
# namespace itself provides uniqueness (one agent per namespace, MVP).
AGENT_RESOURCE_NAME = "agent"

# Give a broken image ~2 minutes to prove itself before the Deployment flips
# Progressing=False / ProgressDeadlineExceeded, which is how we detect
# ImagePullBackOff / CrashLoopBackOff without pod read permissions.
PROGRESS_DEADLINE_SECONDS = 120

PHASE_PENDING = "Pending"
PHASE_DEPLOYING = "Deploying"
PHASE_READY = "Ready"
PHASE_FAILED = "Failed"


def agent_namespace_name(cr_name: str) -> str:
    """Namespace that hosts everything for one LLAgent."""
    return f"agent-{cr_name}"


def agent_hostname(sha: str, agents_domain: str) -> str:
    """Revision hostname: the short SHA becomes the subdomain."""
    return f"{sha}.{agents_domain}"


def agent_url(sha: str, agents_domain: str, url_scheme: str, url_port_suffix: str) -> str:
    """Public base URL reported in status.url."""
    return f"{url_scheme}://{agent_hostname(sha, agents_domain)}{url_port_suffix}"


def common_labels(cr_name: str) -> dict:
    return {
        PART_OF_LABEL: PART_OF_VALUE,
        AGENT_LABEL: cr_name,
        "app.kubernetes.io/managed-by": "ll-operator",
    }


def is_shell(spec: dict) -> bool:
    """A freshly provisioned CR: no image/sha yet — nothing to deploy."""
    return not (spec.get("image") or "").strip() or not (spec.get("sha") or "").strip()


def build_namespace(cr_name: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": agent_namespace_name(cr_name),
            "labels": common_labels(cr_name),
        },
    }


def build_secret(cr_name: str, namespace: str, secret_name: str, age_key_b64: str) -> dict:
    """Copy of the age private key Secret, same name as in the platform ns."""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
            "labels": common_labels(cr_name),
        },
        "type": "Opaque",
        "data": {AGE_KEY_FILENAME: age_key_b64},
    }


def build_deployment(
    cr_name: str,
    namespace: str,
    image: str,
    sha: str,
    key_secret_name: str,
    age_key_mount_path: str = DEFAULT_AGE_KEY_MOUNT_PATH,
) -> dict:
    mount_dir = posixpath.dirname(age_key_mount_path)
    key_file = posixpath.basename(age_key_mount_path)
    selector = {"app.kubernetes.io/name": AGENT_RESOURCE_NAME, AGENT_LABEL: cr_name}
    pod_labels = {**common_labels(cr_name), **selector, f"{GROUP}/sha": sha}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": AGENT_RESOURCE_NAME,
            "namespace": namespace,
            "labels": common_labels(cr_name),
        },
        "spec": {
            "replicas": 1,
            "progressDeadlineSeconds": PROGRESS_DEADLINE_SECONDS,
            "selector": {"matchLabels": selector},
            "template": {
                "metadata": {"labels": pod_labels},
                "spec": {
                    "containers": [
                        {
                            "name": AGENT_RESOURCE_NAME,
                            "image": image,
                            "ports": [{"name": "http", "containerPort": AGENT_PORT}],
                            "env": [
                                # Runtime contract: the entrypoint runs
                                # `sops exec-env keys.env` with the age key here.
                                {"name": "SOPS_AGE_KEY_FILE", "value": age_key_mount_path},
                            ],
                            "volumeMounts": [
                                {
                                    "name": "age-key",
                                    "mountPath": mount_dir,
                                    "readOnly": True,
                                }
                            ],
                            "readinessProbe": {
                                "httpGet": {"path": HEALTH_PATH, "port": AGENT_PORT},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 10,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": HEALTH_PATH, "port": AGENT_PORT},
                                "initialDelaySeconds": 15,
                                "periodSeconds": 20,
                            },
                            "resources": {
                                "requests": {"cpu": "50m", "memory": "256Mi"},
                                "limits": {"memory": "1Gi"},
                            },
                        }
                    ],
                    "volumes": [
                        {
                            "name": "age-key",
                            "secret": {
                                "secretName": key_secret_name,
                                "items": [{"key": AGE_KEY_FILENAME, "path": key_file}],
                            },
                        }
                    ],
                },
            },
        },
    }


def build_service(cr_name: str, namespace: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": AGENT_RESOURCE_NAME,
            "namespace": namespace,
            "labels": common_labels(cr_name),
        },
        "spec": {
            "selector": {
                "app.kubernetes.io/name": AGENT_RESOURCE_NAME,
                AGENT_LABEL: cr_name,
            },
            "ports": [
                {
                    "name": "http",
                    "port": AGENT_PORT,
                    "targetPort": AGENT_PORT,
                    "protocol": "TCP",
                }
            ],
        },
    }


def build_ingress(
    cr_name: str, namespace: str, hosts: list[str], ingress_class_name: str
) -> dict:
    """One rule per host, all for the current revision (its <sha> subdomain on
    each configured agents domain). On sha change the whole rules list is
    replaced (server-side apply), so old <sha> hostnames stop resolving — the
    MVP revision semantics. Multiple hosts is one revision reachable on several
    domains (e.g. the sslip.io admin name and a public wtp.io name), not
    revision history."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": AGENT_RESOURCE_NAME,
            "namespace": namespace,
            "labels": common_labels(cr_name),
        },
        "spec": {
            "ingressClassName": ingress_class_name,
            "rules": [
                {
                    "host": host,
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": AGENT_RESOURCE_NAME,
                                        "port": {"number": AGENT_PORT},
                                    }
                                },
                            }
                        ]
                    },
                }
                for host in hosts
            ],
        },
    }


def build_network_policy(cr_name: str, namespace: str, ingress_namespaces: list[str]) -> dict:
    """One simple policy: ingress only from the ingress-controller
    namespace(s) and from within the agent's own namespace; all egress open
    (agents call external LLM APIs, plus DNS)."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": AGENT_RESOURCE_NAME,
            "namespace": namespace,
            "labels": common_labels(cr_name),
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [
                {
                    "from": [
                        {"podSelector": {}},  # same namespace
                        {
                            "namespaceSelector": {
                                "matchExpressions": [
                                    {
                                        "key": "kubernetes.io/metadata.name",
                                        "operator": "In",
                                        "values": list(ingress_namespaces),
                                    }
                                ]
                            }
                        },
                    ]
                }
            ],
            "egress": [{}],  # allow all
        },
    }


def compute_status(
    spec: dict,
    deployment_status: dict | None,
    agents_domain: str,
    url_scheme: str,
    url_port_suffix: str,
) -> dict:
    """Map spec + observed Deployment status to the LLAgent status contract.

    deployment_status is a plain dict (readyReplicas, conditions[]) or None
    when the agent Deployment does not exist (yet).
    """
    if is_shell(spec):
        return {"phase": PHASE_PENDING, "url": "", "message": ""}

    sha = spec["sha"].strip()
    if deployment_status is None:
        return {"phase": PHASE_DEPLOYING, "url": "", "message": ""}

    conditions = {
        c.get("type"): c for c in (deployment_status.get("conditions") or []) if c.get("type")
    }
    available = conditions.get("Available", {})
    ready_replicas = deployment_status.get("readyReplicas") or 0
    if available.get("status") == "True" or ready_replicas >= 1:
        return {
            "phase": PHASE_READY,
            "url": agent_url(sha, agents_domain, url_scheme, url_port_suffix),
            "message": "",
        }

    # No pod read permission, so image-pull / crash-loop failures surface as
    # the Deployment blowing its progress deadline.
    progressing = conditions.get("Progressing", {})
    if (
        progressing.get("status") == "False"
        and progressing.get("reason") == "ProgressDeadlineExceeded"
    ):
        detail = progressing.get("message") or "deployment exceeded its progress deadline"
        return {
            "phase": PHASE_FAILED,
            "url": "",
            "message": f"revision {sha} failed to roll out: {detail}",
        }

    return {"phase": PHASE_DEPLOYING, "url": "", "message": ""}
