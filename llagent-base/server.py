"""LLAgent runtime wrapper: FastAPI + FastMCP around a user-provided CrewAI crew.

The user's project provides ``/app/crew.py`` exposing a module-level CrewAI
``crew`` object. This server imports it lazily (so the HTTP app always starts,
even when the crew is broken) and exposes it three ways:

- ``GET /healthz``  - liveness/readiness. 200 ``{"ok": true}`` only when the
  crew imported successfully; 503 ``{"ok": false, "error": ...}`` otherwise.
  The pod stays alive (the operator can see the error) but is not Ready.
- ``POST /kickoff`` - REST: ``{"inputs": {...}}`` -> ``{"result": "..."}``.
- ``/mcp``          - FastMCP server exposing a ``kickoff`` tool.

``crew.kickoff`` is synchronous/blocking, so both surfaces run it in a
threadpool to keep the event loop responsive.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

APP_DIR = os.environ.get("LLAGENT_APP_DIR", "/app")
AGENT_NAME = os.environ.get("LLAGENT_NAME", "llagent")

# ---------------------------------------------------------------------------
# Lazy crew loading
#
# The crew is imported on first use (and eagerly at server startup via the
# lifespan) rather than at module import time, so:
#   * the HTTP app always comes up and /healthz can report import failures;
#   * this module is importable without crewai installed (tests stub `crew`).
# ---------------------------------------------------------------------------

_crew_state: dict[str, Any] = {"loaded": False, "crew": None, "error": None}


def _load_crew() -> None:
    """Import ``crew`` from the user's crew.py, recording any failure."""
    _crew_state["loaded"] = True
    _crew_state["crew"] = None
    _crew_state["error"] = None
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    try:
        module = importlib.import_module("crew")
        crew_obj = getattr(module, "crew", None)
        if crew_obj is None:
            raise AttributeError(
                "crew.py was imported but does not define a module-level "
                "'crew' object"
            )
        _crew_state["crew"] = crew_obj
    except Exception as exc:  # noqa: BLE001 - anything can go wrong in user code
        _crew_state["error"] = (
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        )


def _get_crew() -> Any:
    """Return the crew object, or None if it failed to load."""
    if not _crew_state["loaded"]:
        _load_crew()
    return _crew_state["crew"]


def _crew_error() -> str | None:
    if not _crew_state["loaded"]:
        _load_crew()
    return _crew_state["error"]


def _reset_crew() -> None:
    """Force the next access to re-import crew.py (used by tests/reloads)."""
    _crew_state["loaded"] = False
    _crew_state["crew"] = None
    _crew_state["error"] = None


async def _kickoff(inputs: dict[str, Any]) -> str:
    """Run crew.kickoff(inputs=...) in a threadpool; return str(result)."""
    crew = _get_crew()
    if crew is None:
        raise RuntimeError(f"crew is not available: {_crew_error()}")
    result = await run_in_threadpool(crew.kickoff, inputs=inputs)
    return str(result)


# ---------------------------------------------------------------------------
# FastMCP server (mounted at /mcp)
# ---------------------------------------------------------------------------

mcp = FastMCP(AGENT_NAME)


@mcp.tool
async def kickoff(inputs: dict[str, Any] | None = None) -> str:
    """Run this agent's CrewAI crew with the given inputs and return the result."""
    try:
        return await _kickoff(inputs or {})
    except RuntimeError as exc:
        raise ToolError(str(exc)) from exc


# fastmcp ASGI integration: http_app() returns a Starlette app serving the
# streamable-HTTP MCP transport at `path`. It must be mounted with its own
# lifespan running, so the FastAPI lifespan below wraps it.
mcp_app = mcp.http_app(path="/mcp")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Combined lifespan: eagerly load the crew, then run the MCP app's own
    lifespan (required for the streamable-HTTP session manager)."""
    if not _crew_state["loaded"]:
        _load_crew()
    async with mcp_app.lifespan(app):
        yield


class KickoffRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class KickoffResponse(BaseModel):
    result: str


app = FastAPI(
    title=AGENT_NAME,
    description="LLAgent runtime: CrewAI crew behind FastAPI (REST) and FastMCP (/mcp).",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness/readiness.

    200 {"ok": true} when the server is up and the crew imported; 503
    {"ok": false, "error": ...} when crew.py is missing or failed to import.
    The process is alive either way - the operator gates Ready on the 200.
    """
    error = _crew_error()
    if error is None:
        return JSONResponse({"ok": True, "agent": AGENT_NAME})
    return JSONResponse({"ok": False, "agent": AGENT_NAME, "error": error}, status_code=503)


@app.post("/kickoff", response_model=KickoffResponse)
async def kickoff_endpoint(body: KickoffRequest) -> KickoffResponse:
    """Run the crew with the given inputs and return its result as a string."""
    try:
        result = await _kickoff(body.inputs)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return KickoffResponse(result=result)


# Mount the MCP app at the root: FastAPI's own routes (/healthz, /kickoff,
# /docs, /openapi.json) are matched first; everything else - notably /mcp -
# falls through to the FastMCP streamable-HTTP transport.
app.mount("/", mcp_app)
