"""ll-operator: kopf handlers reconciling LLAgent custom resources.

Run (as the Dockerfile does):

    kopf run --standalone -n "$PLATFORM_NAMESPACE" \
        --liveness=http://0.0.0.0:8080/healthz /app/operator/main.py

Reconcile contract (README, frozen for MVP):
  * shell CR (no spec.image / spec.sha)     -> status.phase=Pending
  * image+sha set                           -> namespace agent-<name>, age-key
    Secret copy, Deployment/Service/Ingress/NetworkPolicy; Deploying until the
    Deployment is Available, then Ready + status.url
  * rollout stuck (ProgressDeadlineExceeded, ~120s) or reconcile error
                                            -> Failed + human message
  * sha change                              -> Deployment image updated and the
    Ingress host REPLACED (old <sha> hostnames stop resolving)
  * CR deleted                              -> agent namespace deleted (cascade)
"""

from __future__ import annotations

import dataclasses
import os
import sys

# This file is loaded by path (`kopf run .../main.py`), not as a package —
# and the directory is named `operator`, which deliberately has no
# __init__.py: a regular package of that name would shadow the Python stdlib
# `operator` module (enum imports it at interpreter startup). Import siblings
# flat off this directory instead.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kopf  # noqa: E402

import builders  # noqa: E402
import k8s  # noqa: E402

GROUP = "layernetes.learninglayer.ai"
VERSION = "v1alpha1"
PLURAL = "llagents"

MONITOR_INTERVAL_SECONDS = 10.0
RETRY_DELAY_SECONDS = 30.0


@dataclasses.dataclass(frozen=True)
class Config:
    """Environment injected by the ll-infra chart (ll-operator deployment)."""

    platform_namespace: str
    agents_domain: str
    url_scheme: str
    url_port_suffix: str
    ingress_class_name: str
    age_key_mount_path: str
    ingress_controller_namespaces: tuple[str, ...]

    @classmethod
    def from_env(cls, environ=os.environ) -> "Config":
        controller_ns = environ.get(
            # Not chart-injected (yet): where the ingress controller pods run,
            # for the agent NetworkPolicy. Defaults cover ingress-nginx and
            # k3s/Colima Traefik (kube-system).
            "INGRESS_CONTROLLER_NAMESPACES",
            "ingress-nginx,kube-system",
        )
        return cls(
            platform_namespace=environ.get("PLATFORM_NAMESPACE", "layernetes"),
            agents_domain=environ.get("AGENTS_DOMAIN", "agents.127.0.0.1.sslip.io"),
            url_scheme=environ.get("AGENT_URL_SCHEME", "http"),
            url_port_suffix=environ.get("AGENT_URL_PORT_SUFFIX", ""),
            ingress_class_name=environ.get("INGRESS_CLASS_NAME", "nginx"),
            age_key_mount_path=environ.get(
                "AGE_KEY_MOUNT_PATH", builders.DEFAULT_AGE_KEY_MOUNT_PATH
            ),
            ingress_controller_namespaces=tuple(
                ns.strip() for ns in controller_ns.split(",") if ns.strip()
            ),
        )


@kopf.on.startup()
def startup(settings: kopf.OperatorSettings, logger, **_):
    k8s.load_config()
    settings.persistence.finalizer = f"{GROUP}/finalizer"
    # The LLAgent CRD has a structural schema without unknown-field
    # preservation in status, so kopf's default status-based progress storage
    # would be pruned by the API server. Keep all kopf bookkeeping in
    # annotations instead.
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix=GROUP)
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(
        prefix=GROUP, key="last-handled-configuration"
    )
    logger.info("ll-operator starting: %s", Config.from_env())


def _set_status(patch: kopf.Patch, status: dict) -> None:
    for key, value in status.items():
        patch.status[key] = value


def _apply_agent_resources(name: str, spec: dict, cfg: Config, logger) -> None:
    """Ensure everything for one revision of one agent exists / is current."""
    image = spec["image"].strip()
    sha = spec["sha"].strip()
    key_secret_ref = spec["keySecretRef"]
    namespace = builders.agent_namespace_name(name)

    # 1. The agent's namespace.
    k8s.apply_namespace(builders.build_namespace(name))

    # 2. Copy the age private key from the platform namespace (same name).
    source_data = k8s.get_secret_data(key_secret_ref, cfg.platform_namespace)
    if source_data is None:
        raise ValueError(
            f"age key Secret {key_secret_ref!r} not found in "
            f"namespace {cfg.platform_namespace!r}"
        )
    age_key = source_data.get(builders.AGE_KEY_FILENAME)
    if not age_key:
        raise ValueError(
            f"age key Secret {key_secret_ref!r} has no "
            f"{builders.AGE_KEY_FILENAME!r} data key"
        )
    k8s.apply_secret(builders.build_secret(name, namespace, key_secret_ref, age_key))

    # 3-6. Workload, service, revision-addressed ingress, isolation.
    k8s.apply_deployment(
        builders.build_deployment(
            name,
            namespace,
            image=image,
            sha=sha,
            key_secret_name=key_secret_ref,
            age_key_mount_path=cfg.age_key_mount_path,
        )
    )
    k8s.apply_service(builders.build_service(name, namespace))
    host = builders.agent_hostname(sha, cfg.agents_domain)
    k8s.apply_ingress(builders.build_ingress(name, namespace, host, cfg.ingress_class_name))
    k8s.apply_network_policy(
        builders.build_network_policy(
            name, namespace, list(cfg.ingress_controller_namespaces)
        )
    )
    logger.info("applied resources for %s (sha=%s, host=%s)", name, sha, host)


@kopf.on.create(GROUP, VERSION, PLURAL)
@kopf.on.update(GROUP, VERSION, PLURAL)
@kopf.on.resume(GROUP, VERSION, PLURAL)
def reconcile(name, spec, patch, logger, **_):
    """Main reconcile: create/update the per-agent stack, set the phase."""
    cfg = Config.from_env()
    spec = dict(spec)

    if builders.is_shell(spec):
        _set_status(
            patch, {"phase": builders.PHASE_PENDING, "url": "", "message": ""}
        )
        logger.info("%s is a shell CR (no image/sha yet): Pending", name)
        return

    try:
        _apply_agent_resources(name, spec, cfg, logger)
        deployment_status = k8s.get_deployment_status(
            builders.AGENT_RESOURCE_NAME, builders.agent_namespace_name(name)
        )
    except Exception as exc:
        _set_status(
            patch,
            {"phase": builders.PHASE_FAILED, "url": "", "message": str(exc)},
        )
        raise kopf.TemporaryError(
            f"reconcile of {name} failed: {exc}", delay=RETRY_DELAY_SECONDS
        )

    _set_status(
        patch,
        builders.compute_status(
            spec,
            deployment_status,
            cfg.agents_domain,
            cfg.url_scheme,
            cfg.url_port_suffix,
        ),
    )


@kopf.timer(GROUP, VERSION, PLURAL, interval=MONITOR_INTERVAL_SECONDS, initial_delay=5.0)
def monitor(name, spec, status, patch, logger, **_):
    """Keep status.phase current by observing the agent Deployment.

    Deployment conditions are our only failure signal (no pod read RBAC):
    a bad image or crash loop trips progressDeadlineSeconds (120s) and shows
    up as Progressing=False / ProgressDeadlineExceeded.
    """
    cfg = Config.from_env()
    spec = dict(spec)
    current = {
        "phase": (status or {}).get("phase"),
        "url": (status or {}).get("url") or "",
        "message": (status or {}).get("message") or "",
    }

    if builders.is_shell(spec):
        desired = {"phase": builders.PHASE_PENDING, "url": "", "message": ""}
    else:
        deployment_status = k8s.get_deployment_status(
            builders.AGENT_RESOURCE_NAME, builders.agent_namespace_name(name)
        )
        if deployment_status is None and current["phase"] == builders.PHASE_FAILED:
            # A reconcile error (e.g. missing age key Secret) set Failed and
            # is being retried; don't overwrite its message with "Deploying".
            return
        desired = builders.compute_status(
            spec,
            deployment_status,
            cfg.agents_domain,
            cfg.url_scheme,
            cfg.url_port_suffix,
        )

    if desired != current:
        _set_status(patch, desired)
        logger.info("%s: %s -> %s", name, current["phase"], desired["phase"])


@kopf.on.delete(GROUP, VERSION, PLURAL)
def delete(name, logger, **_):
    """kopf's finalizer keeps the CR until this succeeds; deleting the agent
    namespace cascades the Deployment/Service/Ingress/Secret/NetworkPolicy."""
    namespace = builders.agent_namespace_name(name)
    k8s.delete_namespace(namespace)
    logger.info("deleted namespace %s for %s", namespace, name)
