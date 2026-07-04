"""Test fixtures for the llagent-base server wrapper.

crewai is deliberately NOT installed in the test venv: the crew is stubbed by
injecting a fake ``crew`` module into ``sys.modules``. server.py imports the
crew lazily, so it is importable (and testable) without crewai.
"""

from __future__ import annotations

import sys
import types

import pytest
from starlette.testclient import TestClient

import server


class StubCrew:
    """Minimal stand-in for a CrewAI Crew: sync, blocking kickoff()."""

    def __init__(self, result="stub-result"):
        self.result = result
        self.calls: list[dict] = []

    def kickoff(self, inputs=None):
        self.calls.append(inputs)
        return self.result


@pytest.fixture(autouse=True)
def reset_crew_state():
    """Ensure each test starts with no cached crew and no stub module."""
    server._reset_crew()
    sys.modules.pop("crew", None)
    yield
    server._reset_crew()
    sys.modules.pop("crew", None)


@pytest.fixture
def stub_crew(monkeypatch):
    """Inject a working stub crew module as sys.modules['crew']."""
    crew_obj = StubCrew()
    module = types.ModuleType("crew")
    module.crew = crew_obj
    monkeypatch.setitem(sys.modules, "crew", module)
    return crew_obj


@pytest.fixture
def client(stub_crew):
    """TestClient with a healthy stub crew (lifespan runs -> MCP app works)."""
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def broken_client(monkeypatch):
    """TestClient whose crew.py import fails."""

    def boom(name, *args, **kwargs):
        raise ImportError("No module named 'crew' (simulated)")

    monkeypatch.setattr(server.importlib, "import_module", boom)
    with TestClient(server.app) as c:
        yield c
