"""Tests for the llagent-base FastAPI/FastMCP wrapper (server.py)."""

from __future__ import annotations

import sys
import types

from starlette.testclient import TestClient

import server


def test_healthz_ok_with_crew(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["agent"] == server.AGENT_NAME


def test_healthz_503_when_crew_import_fails(broken_client):
    r = broken_client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert "simulated" in body["error"]


def test_healthz_503_when_crew_attribute_missing(monkeypatch):
    # crew.py imports fine but has no module-level `crew` object.
    module = types.ModuleType("crew")
    monkeypatch.setitem(sys.modules, "crew", module)
    with TestClient(server.app) as c:
        r = c.get("/healthz")
    assert r.status_code == 503
    assert "crew" in r.json()["error"]


def test_kickoff_calls_crew_and_returns_result(client, stub_crew):
    stub_crew.result = "the answer is 42"
    r = client.post("/kickoff", json={"inputs": {"topic": "meaning of life"}})
    assert r.status_code == 200
    assert r.json() == {"result": "the answer is 42"}
    assert stub_crew.calls == [{"topic": "meaning of life"}]


def test_kickoff_defaults_to_empty_inputs(client, stub_crew):
    r = client.post("/kickoff", json={})
    assert r.status_code == 200
    assert stub_crew.calls == [{}]


def test_kickoff_result_is_stringified(client, stub_crew):
    stub_crew.result = {"raw": "not a string"}
    r = client.post("/kickoff", json={"inputs": {}})
    assert r.status_code == 200
    assert r.json()["result"] == str({"raw": "not a string"})


def test_kickoff_503_when_crew_unavailable(broken_client):
    r = broken_client.post("/kickoff", json={"inputs": {}})
    assert r.status_code == 503
    assert "crew is not available" in r.json()["detail"]


def test_docs_served(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_mcp_mounted_not_404(client):
    # A bare request without MCP accept headers must reach the MCP transport
    # (406 Not Acceptable from streamable-HTTP), not fall through to a 404.
    r = client.post("/mcp", json={})
    assert r.status_code != 404
    assert r.status_code in (400, 406)
    assert "accept" in r.text.lower() or "jsonrpc" in r.text.lower()


def test_mcp_get_is_mcp_ish(client):
    r = client.get("/mcp")
    assert r.status_code in (400, 405, 406)


def test_mcp_kickoff_tool_via_client(stub_crew):
    # Full round-trip through the mounted MCP app with a real MCP client.
    import anyio
    from fastmcp import Client

    stub_crew.result = "mcp says hi"

    async def run():
        async with Client(server.mcp) as mcp_client:
            tools = await mcp_client.list_tools()
            assert "kickoff" in [t.name for t in tools]
            result = await mcp_client.call_tool("kickoff", {"inputs": {"x": 1}})
            return result

    result = anyio.run(run)
    assert "mcp says hi" in str(result.content[0].text)
    assert stub_crew.calls == [{"x": 1}]
