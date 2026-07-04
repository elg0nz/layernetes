"""Handler-level tests for main.py with the k8s layer mocked out."""

import logging
from unittest import mock

import kopf
import pytest

import builders
import main

LOGGER = logging.getLogger("test")

ENV = {
    "PLATFORM_NAMESPACE": "layernetes",
    "AGENTS_DOMAIN": "agents.learninglayer.ai",
    "AGENT_URL_SCHEME": "https",
    "AGENT_URL_PORT_SUFFIX": "",
    "INGRESS_CLASS_NAME": "nginx",
    "AGE_KEY_MOUNT_PATH": "/var/run/secrets/llnate/age.key",
}

SPEC = {
    "owner": "gonz",
    "repo": "gonz/hello-agent",
    "image": "gitea.example/gonz/hello-agent:3f2a91c",
    "sha": "3f2a91c",
    "keySecretRef": "age-key-gonz",
}


class FakePatch:
    def __init__(self):
        self.status = {}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def fake_k8s(monkeypatch):
    fake = mock.Mock(spec_set=[
        "apply_namespace", "apply_secret", "apply_deployment", "apply_service",
        "apply_ingress", "apply_network_policy", "get_secret_data",
        "get_deployment_status", "delete_namespace", "load_config",
    ])
    fake.get_secret_data.return_value = {"age.key": "QUdFLUtFWQ=="}
    fake.get_deployment_status.return_value = None
    monkeypatch.setattr(main, "k8s", fake)
    return fake


def test_config_from_env():
    cfg = main.Config.from_env()
    assert cfg.platform_namespace == "layernetes"
    assert cfg.agents_domain == "agents.learninglayer.ai"
    assert cfg.ingress_controller_namespaces == ("ingress-nginx", "kube-system")


def test_shell_cr_goes_pending_and_touches_nothing(fake_k8s):
    patch = FakePatch()
    shell_spec = {"owner": "gonz", "repo": "gonz/hello-agent", "keySecretRef": "age-key-gonz"}
    main.reconcile(name="gonz-hello-agent", spec=shell_spec, patch=patch, logger=LOGGER)
    assert patch.status == {"phase": "Pending", "url": "", "message": ""}
    fake_k8s.apply_namespace.assert_not_called()
    fake_k8s.apply_deployment.assert_not_called()


def test_full_reconcile_applies_stack_and_reports_deploying(fake_k8s):
    patch = FakePatch()
    main.reconcile(name="gonz-hello-agent", spec=SPEC, patch=patch, logger=LOGGER)

    fake_k8s.apply_namespace.assert_called_once()
    ns_body = fake_k8s.apply_namespace.call_args.args[0]
    assert ns_body["metadata"]["name"] == "agent-gonz-hello-agent"

    fake_k8s.get_secret_data.assert_called_once_with("age-key-gonz", "layernetes")
    secret_body = fake_k8s.apply_secret.call_args.args[0]
    assert secret_body["metadata"]["namespace"] == "agent-gonz-hello-agent"
    assert secret_body["data"] == {"age.key": "QUdFLUtFWQ=="}

    dep_body = fake_k8s.apply_deployment.call_args.args[0]
    assert dep_body["spec"]["template"]["spec"]["containers"][0]["image"] == SPEC["image"]

    ing_body = fake_k8s.apply_ingress.call_args.args[0]
    assert ing_body["spec"]["rules"][0]["host"] == "3f2a91c.agents.learninglayer.ai"
    assert ing_body["spec"]["ingressClassName"] == "nginx"

    fake_k8s.apply_service.assert_called_once()
    fake_k8s.apply_network_policy.assert_called_once()

    # Deployment not observed yet -> Deploying.
    assert patch.status == {"phase": "Deploying", "url": "", "message": ""}


def test_reconcile_ready_sets_url(fake_k8s):
    fake_k8s.get_deployment_status.return_value = {
        "readyReplicas": 1,
        "conditions": [{"type": "Available", "status": "True"}],
    }
    patch = FakePatch()
    main.reconcile(name="gonz-hello-agent", spec=SPEC, patch=patch, logger=LOGGER)
    assert patch.status == {
        "phase": "Ready",
        "url": "https://3f2a91c.agents.learninglayer.ai",
        "message": "",
    }


def test_missing_age_key_secret_fails_and_retries(fake_k8s):
    fake_k8s.get_secret_data.return_value = None
    patch = FakePatch()
    with pytest.raises(kopf.TemporaryError):
        main.reconcile(name="gonz-hello-agent", spec=SPEC, patch=patch, logger=LOGGER)
    assert patch.status["phase"] == "Failed"
    assert "age-key-gonz" in patch.status["message"]
    fake_k8s.apply_deployment.assert_not_called()


def test_monitor_updates_phase_on_progress_deadline(fake_k8s):
    fake_k8s.get_deployment_status.return_value = {
        "readyReplicas": 0,
        "conditions": [
            {
                "type": "Progressing",
                "status": "False",
                "reason": "ProgressDeadlineExceeded",
                "message": "timed out",
            }
        ],
    }
    patch = FakePatch()
    main.monitor(
        name="gonz-hello-agent",
        spec=SPEC,
        status={"phase": "Deploying", "url": "", "message": ""},
        patch=patch,
        logger=LOGGER,
    )
    assert patch.status["phase"] == "Failed"
    assert "timed out" in patch.status["message"]


def test_monitor_is_a_noop_when_status_is_current(fake_k8s):
    fake_k8s.get_deployment_status.return_value = {
        "readyReplicas": 1,
        "conditions": [{"type": "Available", "status": "True"}],
    }
    patch = FakePatch()
    main.monitor(
        name="gonz-hello-agent",
        spec=SPEC,
        status={
            "phase": "Ready",
            "url": "https://3f2a91c.agents.learninglayer.ai",
            "message": "",
        },
        patch=patch,
        logger=LOGGER,
    )
    assert patch.status == {}  # no patch -> no API churn every 10s


def test_monitor_preserves_reconcile_failure_when_deployment_absent(fake_k8s):
    fake_k8s.get_deployment_status.return_value = None
    patch = FakePatch()
    main.monitor(
        name="gonz-hello-agent",
        spec=SPEC,
        status={"phase": "Failed", "url": "", "message": "age key Secret missing"},
        patch=patch,
        logger=LOGGER,
    )
    assert patch.status == {}  # keeps Failed + message while reconcile retries


def test_delete_removes_agent_namespace(fake_k8s):
    main.delete(name="gonz-hello-agent", logger=LOGGER)
    fake_k8s.delete_namespace.assert_called_once_with("agent-gonz-hello-agent")
