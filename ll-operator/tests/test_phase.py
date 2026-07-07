"""Phase logic: spec + observed Deployment status -> LLAgent status."""

import builders

SPEC = {
    "owner": "gonz",
    "repo": "gonz/hello-agent",
    "image": "gitea.example/gonz/hello-agent:3f2a91c",
    "sha": "3f2a91c",
    "keySecretRef": "age-key-gonz",
}
URL_ARGS = dict(
    agents_domain="agents.layernetes.learninglayer.ai",
    url_scheme="https",
    url_port_suffix="",
)


def compute(spec, deployment_status):
    return builders.compute_status(spec, deployment_status, **URL_ARGS)


def test_shell_cr_is_pending():
    shell = {"owner": "gonz", "repo": "gonz/hello-agent", "keySecretRef": "age-key-gonz"}
    assert compute(shell, None) == {"phase": "Pending", "url": "", "message": ""}
    # Deployment status is irrelevant for a shell CR.
    assert compute({**shell, "image": ""}, {"readyReplicas": 1})["phase"] == "Pending"


def test_no_deployment_yet_is_deploying():
    assert compute(SPEC, None) == {"phase": "Deploying", "url": "", "message": ""}


def test_rollout_in_progress_is_deploying():
    status = {
        "readyReplicas": 0,
        "conditions": [
            {"type": "Available", "status": "False", "reason": "MinimumReplicasUnavailable"},
            {"type": "Progressing", "status": "True", "reason": "ReplicaSetUpdated"},
        ],
    }
    assert compute(SPEC, status)["phase"] == "Deploying"


def test_available_condition_is_ready_with_url():
    status = {
        "readyReplicas": 1,
        "conditions": [{"type": "Available", "status": "True", "reason": "MinimumReplicasAvailable"}],
    }
    result = compute(SPEC, status)
    assert result["phase"] == "Ready"
    assert result["url"] == "https://3f2a91c.agents.layernetes.learninglayer.ai"
    assert result["message"] == ""


def test_ready_replicas_alone_is_ready():
    assert compute(SPEC, {"readyReplicas": 1, "conditions": []})["phase"] == "Ready"


def test_ready_url_respects_scheme_and_port_suffix():
    status = {"readyReplicas": 1, "conditions": []}
    result = builders.compute_status(
        SPEC,
        status,
        agents_domain="agents.127.0.0.1.sslip.io",
        url_scheme="http",
        url_port_suffix=":8080",
    )
    assert result["url"] == "http://3f2a91c.agents.127.0.0.1.sslip.io:8080"


def test_progress_deadline_exceeded_is_failed_with_message():
    status = {
        "readyReplicas": 0,
        "conditions": [
            {"type": "Available", "status": "False", "reason": "MinimumReplicasUnavailable"},
            {
                "type": "Progressing",
                "status": "False",
                "reason": "ProgressDeadlineExceeded",
                "message": 'ReplicaSet "agent-abc" has timed out progressing.',
            },
        ],
    }
    result = compute(SPEC, status)
    assert result["phase"] == "Failed"
    assert result["url"] == ""
    assert "3f2a91c" in result["message"]
    assert "timed out progressing" in result["message"]


def test_progressing_false_other_reason_is_not_failed():
    status = {
        "readyReplicas": 0,
        "conditions": [{"type": "Progressing", "status": "False", "reason": "Something"}],
    }
    assert compute(SPEC, status)["phase"] == "Deploying"
