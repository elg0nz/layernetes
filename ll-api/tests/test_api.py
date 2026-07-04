import base64
import json

import httpx

from app.kube import PUBLIC_KEY_ANNOTATION


def seed_agent(cr_store, secret_store, owner="gonz", name="hello-agent", ci_token="ci-tok", status=None):
    """Drop an already-provisioned agent straight into the fake stores."""
    from kubernetes import client as k8s

    cr_name = f"{owner}-{name}"
    cr = {
        "apiVersion": "layernetes.learninglayer.ai/v1alpha1",
        "kind": "LLAgent",
        "metadata": {"name": cr_name, "namespace": "layernetes"},
        "spec": {"owner": owner, "repo": f"{owner}/{name}", "keySecretRef": f"age-key-{owner}"},
    }
    if status is not None:
        cr["status"] = status
    cr_store[cr_name] = cr
    secret_store[f"ll-ci-token-{cr_name}"] = k8s.V1Secret(
        metadata=k8s.V1ObjectMeta(name=f"ll-ci-token-{cr_name}"),
        data={"token": base64.b64encode(ci_token.encode()).decode()},
    )
    return cr_name


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


class TestLogin:
    def test_success(self, client, gitea_mock):
        route = gitea_mock.post("/api/v1/users/gonz/tokens").respond(201, json={"sha1": "tok-abc"})
        resp = client.post("/v1/auth/login", json={"username": "gonz", "password": "pw"})
        assert resp.status_code == 200
        assert resp.json() == {"token": "tok-abc", "username": "gonz"}
        request = route.calls.last.request
        assert request.headers["Authorization"].startswith("Basic ")
        sent = json.loads(request.content)
        assert set(sent["scopes"]) == {"write:repository", "write:package", "write:user"}

    def test_bad_credentials(self, client, gitea_mock):
        gitea_mock.post("/api/v1/users/gonz/tokens").respond(401, json={"message": "denied"})
        resp = client.post("/v1/auth/login", json={"username": "gonz", "password": "nope"})
        assert resp.status_code == 401


class TestMe:
    def test_no_key_yet(self, client, as_user):
        headers, _ = as_user()
        resp = client.get("/v1/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"username": "gonz", "age_public_key": ""}

    def test_with_key(self, client, as_user, kube):
        headers, _ = as_user()
        kube.create_secret(
            "age-key-gonz",
            {"age.key": "# public key: age1abc\nAGE-SECRET-KEY-1XYZ\n"},
            annotations={PUBLIC_KEY_ANNOTATION: "age1abc"},
        )
        resp = client.get("/v1/me", headers=headers)
        assert resp.json() == {"username": "gonz", "age_public_key": "age1abc"}

    def test_requires_auth(self, client):
        assert client.get("/v1/me").status_code == 401

    def test_rejects_bad_token(self, client, gitea_mock):
        gitea_mock.get("/api/v1/user").respond(401, json={"message": "bad token"})
        resp = client.get("/v1/me", headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 401


class TestProvision:
    def mock_gitea_provisioning(self, gitea_mock, owner="gonz", name="hello-agent"):
        routes = {
            "repo": gitea_mock.post("/api/v1/user/repos").respond(
                201, json={"full_name": f"{owner}/{name}"}
            ),
            "secret": gitea_mock.put(
                f"/api/v1/repos/{owner}/{name}/actions/secrets/LL_API_TOKEN"
            ).respond(201),
            "var_api": gitea_mock.post(
                f"/api/v1/repos/{owner}/{name}/actions/variables/LL_API_URL"
            ).respond(201),
            "var_reg": gitea_mock.post(
                f"/api/v1/repos/{owner}/{name}/actions/variables/REGISTRY"
            ).respond(201),
            "secret_reg_user": gitea_mock.put(
                f"/api/v1/repos/{owner}/{name}/actions/secrets/REGISTRY_USER"
            ).respond(201),
            "secret_reg_password": gitea_mock.put(
                f"/api/v1/repos/{owner}/{name}/actions/secrets/REGISTRY_PASSWORD"
            ).respond(201),
        }
        return routes

    def test_full_flow(self, client, as_user, gitea_mock, secret_store, cr_store):
        headers, _ = as_user()
        routes = self.mock_gitea_provisioning(gitea_mock)

        resp = client.post("/v1/agents", json={"name": "hello-agent"}, headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "gonz-hello-agent"
        assert body["repo"] == "gonz/hello-agent"
        assert body["clone_url"] == "http://gitea.127.0.0.1.sslip.io:8080/gonz/hello-agent.git"
        assert body["age_public_key"].startswith("age1")

        # age key Secret: identity file + public-key annotation
        age_secret = secret_store["age-key-gonz"]
        key_file = base64.b64decode(age_secret.data["age.key"]).decode()
        assert "AGE-SECRET-KEY-" in key_file
        assert age_secret.metadata.annotations[PUBLIC_KEY_ANNOTATION] == body["age_public_key"]

        # CI token Secret matches the Actions secret Gitea received
        ci_token = base64.b64decode(secret_store["ll-ci-token-gonz-hello-agent"].data["token"]).decode()
        assert json.loads(routes["secret"].calls.last.request.content) == {"data": ci_token}

        # Actions variables
        assert json.loads(routes["var_api"].calls.last.request.content) == {
            "value": "http://ll-api.layernetes.svc.cluster.local:8000"
        }
        assert json.loads(routes["var_reg"].calls.last.request.content) == {
            "value": "gitea.127.0.0.1.sslip.io:8080"
        }

        # LLAgent shell CR
        cr = cr_store["gonz-hello-agent"]
        assert cr["spec"] == {
            "owner": "gonz",
            "repo": "gonz/hello-agent",
            "keySecretRef": "age-key-gonz",
        }
        assert "image" not in cr["spec"]

        # repo created with auto_init disabled, using the caller's token
        repo_req = routes["repo"].calls.last.request
        assert repo_req.headers["Authorization"] == "token user-token-123"
        assert json.loads(repo_req.content)["auto_init"] is False

    def test_idempotent_rerun(self, client, as_user, gitea_mock, secret_store, cr_store):
        headers, _ = as_user()
        self.mock_gitea_provisioning(gitea_mock)
        first = client.post("/v1/agents", json={"name": "hello-agent"}, headers=headers).json()

        # second run: repo already exists (409), everything else reused
        gitea_mock.post("/api/v1/user/repos").respond(409, json={"message": "exists"})
        second = client.post("/v1/agents", json={"name": "hello-agent"}, headers=headers)
        assert second.status_code == 201
        assert second.json() == first
        assert len(cr_store) == 1

    def test_gitea_failure_maps_to_400(self, client, as_user, gitea_mock):
        headers, _ = as_user()
        gitea_mock.post("/api/v1/user/repos").respond(422, json={"message": "bad repo name"})
        resp = client.post("/v1/agents", json={"name": "hello-agent"}, headers=headers)
        assert resp.status_code == 400
        assert "bad repo name" in resp.json()["detail"]

    def test_invalid_name_rejected(self, client, as_user):
        headers, _ = as_user()
        resp = client.post("/v1/agents", json={"name": "Bad_Name!"}, headers=headers)
        assert resp.status_code == 422


class TestBuilds:
    def test_callback_updates_spec(self, client, secret_store, cr_store):
        name = seed_agent(cr_store, secret_store, ci_token="ci-tok")
        resp = client.post(
            f"/v1/agents/{name}/builds",
            json={"sha": "3f2a91c", "image": "gitea.example/gonz/hello-agent:3f2a91c"},
            headers={"Authorization": "Bearer ci-tok"},
        )
        assert resp.status_code == 200
        assert cr_store[name]["spec"]["sha"] == "3f2a91c"
        assert cr_store[name]["spec"]["image"] == "gitea.example/gonz/hello-agent:3f2a91c"

    def test_rejects_bad_ci_token(self, client, secret_store, cr_store):
        name = seed_agent(cr_store, secret_store, ci_token="ci-tok")
        resp = client.post(
            f"/v1/agents/{name}/builds",
            json={"sha": "3f2a91c", "image": "img"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401
        assert "sha" not in cr_store[name]["spec"]

    def test_rejects_unknown_agent(self, client):
        resp = client.post(
            "/v1/agents/nobody-nothing/builds",
            json={"sha": "abc", "image": "img"},
            headers={"Authorization": "Bearer whatever"},
        )
        assert resp.status_code == 401

    def test_requires_token(self, client, secret_store, cr_store):
        name = seed_agent(cr_store, secret_store)
        resp = client.post(f"/v1/agents/{name}/builds", json={"sha": "a", "image": "i"})
        assert resp.status_code == 401


class TestStatus:
    def test_pending_when_no_status(self, client, as_user, secret_store, cr_store):
        headers, _ = as_user()
        name = seed_agent(cr_store, secret_store)
        resp = client.get(f"/v1/agents/{name}/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"phase": "Pending", "url": "", "message": ""}

    def test_passthrough_and_short_name(self, client, as_user, secret_store, cr_store):
        headers, _ = as_user()
        seed_agent(
            cr_store,
            secret_store,
            status={"phase": "Ready", "url": "http://3f2a91c.agents.127.0.0.1.sslip.io:8080"},
        )
        resp = client.get("/v1/agents/hello-agent/status", headers=headers)
        assert resp.json() == {
            "phase": "Ready",
            "url": "http://3f2a91c.agents.127.0.0.1.sslip.io:8080",
            "message": "",
        }

    def test_owner_only(self, client, as_user, secret_store, cr_store):
        headers, _ = as_user(username="mallory")
        name = seed_agent(cr_store, secret_store, owner="gonz")
        resp = client.get(f"/v1/agents/{name}/status", headers=headers)
        assert resp.status_code == 404


class TestDelete:
    def test_teardown(self, client, as_user, gitea_mock, kube, secret_store, cr_store):
        headers, _ = as_user()
        name = seed_agent(cr_store, secret_store)
        kube.create_secret("age-key-gonz", {"age.key": "AGE-SECRET-KEY-1XYZ\n"})
        repo_route = gitea_mock.delete("/api/v1/repos/gonz/hello-agent").respond(204)

        resp = client.delete(f"/v1/agents/{name}", headers=headers)
        assert resp.status_code == 204
        assert name not in cr_store
        assert f"ll-ci-token-{name}" not in secret_store
        assert repo_route.called
        # the per-user age key survives
        assert "age-key-gonz" in secret_store

    def test_owner_only(self, client, as_user, gitea_mock, secret_store, cr_store):
        headers, _ = as_user(username="mallory")
        name = seed_agent(cr_store, secret_store, owner="gonz")
        resp = client.delete(f"/v1/agents/{name}", headers=headers)
        assert resp.status_code == 404
        assert name in cr_store

    def test_missing_agent(self, client, as_user):
        headers, _ = as_user()
        assert client.delete("/v1/agents/ghost", headers=headers).status_code == 404
