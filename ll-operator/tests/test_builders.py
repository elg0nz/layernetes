"""Unit tests pinning the builders to the frozen MVP contract."""

import builders

CR_NAME = "gonz-hello-agent"
NS = "agent-gonz-hello-agent"
IMAGE = "gitea.example/gonz/hello-agent:3f2a91c"
SHA = "3f2a91c"
KEY_SECRET = "age-key-gonz"
DOMAIN = "agents.learninglayer.ai"


def test_agent_namespace_name():
    assert builders.agent_namespace_name(CR_NAME) == NS


def test_agent_hostname_and_url():
    assert builders.agent_hostname(SHA, DOMAIN) == "3f2a91c.agents.learninglayer.ai"
    assert (
        builders.agent_url(SHA, DOMAIN, "https", "")
        == "https://3f2a91c.agents.learninglayer.ai"
    )
    assert (
        builders.agent_url(SHA, "agents.127.0.0.1.sslip.io", "http", ":8080")
        == "http://3f2a91c.agents.127.0.0.1.sslip.io:8080"
    )


def test_is_shell():
    assert builders.is_shell({})
    assert builders.is_shell({"image": "", "sha": ""})
    assert builders.is_shell({"image": IMAGE})  # sha missing
    assert builders.is_shell({"sha": SHA})  # image missing
    assert not builders.is_shell({"image": IMAGE, "sha": SHA})


def test_namespace_labels():
    ns = builders.build_namespace(CR_NAME)
    assert ns["metadata"]["name"] == NS
    labels = ns["metadata"]["labels"]
    assert labels["app.kubernetes.io/part-of"] == "layernetes"
    assert labels["layernetes.learninglayer.ai/agent"] == CR_NAME


def test_secret_copy_shape():
    secret = builders.build_secret(CR_NAME, NS, KEY_SECRET, "QUdFLUtFWQ==")
    assert secret["metadata"]["name"] == KEY_SECRET  # same name as source
    assert secret["metadata"]["namespace"] == NS
    assert secret["data"] == {"age.key": "QUdFLUtFWQ=="}
    assert secret["type"] == "Opaque"


def _deployment():
    return builders.build_deployment(
        CR_NAME, NS, image=IMAGE, sha=SHA, key_secret_name=KEY_SECRET
    )


def test_deployment_identity_and_image():
    dep = _deployment()
    assert dep["metadata"]["name"] == "agent"
    assert dep["metadata"]["namespace"] == NS
    container = dep["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == IMAGE
    assert container["ports"] == [{"name": "http", "containerPort": 8000}]


def test_deployment_selector_matches_pod_labels():
    dep = _deployment()
    selector = dep["spec"]["selector"]["matchLabels"]
    pod_labels = dep["spec"]["template"]["metadata"]["labels"]
    assert selector.items() <= pod_labels.items()


def test_deployment_age_key_mount_contract():
    dep = _deployment()
    container = dep["spec"]["template"]["spec"]["containers"][0]
    assert {"name": "SOPS_AGE_KEY_FILE", "value": "/var/run/secrets/llnate/age.key"} in (
        container["env"]
    )
    mount = container["volumeMounts"][0]
    assert mount["mountPath"] == "/var/run/secrets/llnate"
    assert mount["readOnly"] is True
    volume = dep["spec"]["template"]["spec"]["volumes"][0]
    assert volume["name"] == mount["name"]
    assert volume["secret"]["secretName"] == KEY_SECRET
    assert volume["secret"]["items"] == [{"key": "age.key", "path": "age.key"}]


def test_deployment_probes_and_resources():
    container = _deployment()["spec"]["template"]["spec"]["containers"][0]
    for probe in ("readinessProbe", "livenessProbe"):
        http_get = container[probe]["httpGet"]
        assert http_get == {"path": "/healthz", "port": 8000}
    assert container["resources"]["requests"] == {"cpu": "50m", "memory": "256Mi"}
    assert container["resources"]["limits"] == {"memory": "1Gi"}


def test_deployment_progress_deadline():
    # No pod RBAC: ImagePullBackOff/CrashLoopBackOff must surface as
    # ProgressDeadlineExceeded within ~2 minutes.
    assert _deployment()["spec"]["progressDeadlineSeconds"] == 120


def test_service_shape():
    svc = builders.build_service(CR_NAME, NS)
    assert svc["metadata"]["name"] == "agent"
    port = svc["spec"]["ports"][0]
    assert port["port"] == 8000
    assert port["targetPort"] == 8000
    dep_selector = _deployment()["spec"]["selector"]["matchLabels"]
    assert svc["spec"]["selector"] == dep_selector


def test_ingress_shape():
    host = builders.agent_hostname(SHA, DOMAIN)
    ing = builders.build_ingress(CR_NAME, NS, host, "nginx")
    assert ing["metadata"]["name"] == "agent"
    assert ing["spec"]["ingressClassName"] == "nginx"
    rules = ing["spec"]["rules"]
    assert len(rules) == 1  # only the latest revision resolves (MVP)
    assert rules[0]["host"] == "3f2a91c.agents.learninglayer.ai"
    path = rules[0]["http"]["paths"][0]
    assert path["path"] == "/"
    assert path["pathType"] == "Prefix"
    assert path["backend"]["service"] == {"name": "agent", "port": {"number": 8000}}


def test_network_policy():
    netpol = builders.build_network_policy(CR_NAME, NS, ["ingress-nginx", "kube-system"])
    spec = netpol["spec"]
    assert spec["podSelector"] == {}
    assert sorted(spec["policyTypes"]) == ["Egress", "Ingress"]
    assert spec["egress"] == [{}]  # agents call external LLM APIs
    froms = spec["ingress"][0]["from"]
    assert {"podSelector": {}} in froms  # same namespace
    ns_selector = next(f for f in froms if "namespaceSelector" in f)
    expr = ns_selector["namespaceSelector"]["matchExpressions"][0]
    assert expr["key"] == "kubernetes.io/metadata.name"
    assert expr["operator"] == "In"
    assert set(expr["values"]) == {"ingress-nginx", "kube-system"}
