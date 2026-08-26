"""FastAPI app — the HTTP surface for SOPilot.

Endpoints:
  GET  /health           liveness + whether an LLM key is configured
  GET  /tools            list the available (mock) tools
  POST /compile          SOP text -> graph OR clarifying questions (+ validation)
  POST /validate         validate a graph the user may have edited
  POST /run              execute a graph against an entry input -> trace
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import library
from app.compiler import compile_sop
from app.config import get_settings
from app.graph_schema import GraphDocument
from app.runtime import run_graph
from app.tools import ACTION_LOG, CASE_DEFAULTS, TOOL_REGISTRY, set_case
from app.validator import validate_graph

settings = get_settings()
app = FastAPI(title="SOPilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request models ──
class CompileRequest(BaseModel):
    sop_text: str
    answers: Optional[dict[str, str]] = None


class ValidateRequest(BaseModel):
    graph: dict[str, Any]


class RunRequest(BaseModel):
    graph: dict[str, Any]
    entry: dict[str, Any] = {}
    # The facts about this specific case (drive different decision branches).
    case: dict[str, Any] = {}


class SaveRequest(BaseModel):
    title: str
    sop_text: str
    graph: dict[str, Any]


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm_configured": settings.has_llm,
            "mode": "gemini" if settings.has_llm else "mock"}


@app.get("/tools")
def list_tools() -> dict[str, Any]:
    return {"tools": [
        {"name": t.name, "description": t.description, "params": t.params,
         "case_fields": t.case_fields}
        for t in TOOL_REGISTRY.values()
    ]}


@app.post("/compile")
def compile_endpoint(req: CompileRequest) -> dict[str, Any]:
    result = compile_sop(req.sop_text, req.answers)
    payload = result.to_dict()
    # If we produced a graph, run validation and attach any problems.
    if result.kind == "graph" and result.graph is not None:
        payload["validation"] = validate_graph(result.graph)
    return payload


@app.post("/validate")
def validate_endpoint(req: ValidateRequest) -> dict[str, Any]:
    try:
        graph = GraphDocument.model_validate(req.graph)
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "problems": [f"schema error: {e}"]}
    problems = validate_graph(graph)
    return {"valid": not problems, "problems": problems}


@app.post("/run")
def run_endpoint(req: RunRequest) -> dict[str, Any]:
    try:
        graph = GraphDocument.model_validate(req.graph)
    except Exception as e:  # noqa: BLE001
        return {"error": f"invalid graph: {e}"}
    problems = validate_graph(graph)
    if problems:
        return {"error": "graph failed validation", "problems": problems}

    ACTION_LOG.clear()
    set_case(req.case)          # seed the mock tools with this case's facts
    result = run_graph(graph, req.entry)
    result["action_log"] = list(ACTION_LOG)
    return result


@app.get("/case-defaults")
def case_defaults() -> dict[str, Any]:
    """The editable case fields + defaults, so the UI can prefill the case editor."""
    return {"defaults": CASE_DEFAULTS}


# ── Router + Agent Mode ──
class HandleRequest(BaseModel):
    case_text: str
    entry: dict[str, Any] = {}
    case: dict[str, Any] = {}
    force_agent: bool = False


@app.post("/handle")
def handle_endpoint(req: HandleRequest) -> dict[str, Any]:
    """Front door: route a case to the deterministic workflow or the agent."""
    from app.router import handle_case
    return handle_case(req.case_text, req.entry, req.case, req.force_agent)


class AgentRequest(BaseModel):
    case_text: str
    entry: dict[str, Any] = {}
    case: dict[str, Any] = {}
    policy_text: str = ""


@app.post("/agent-run")
def agent_endpoint(req: AgentRequest) -> dict[str, Any]:
    """Run the tool-using agent directly on a case (force agent mode)."""
    from app.agent import run_agent
    return run_agent(req.case_text, req.entry, req.case, req.policy_text)


# ── SOP library (a company's collection of procedures) ──
@app.get("/samples")
def samples() -> dict[str, Any]:
    return {"samples": library.SAMPLE_SOPS}


@app.get("/library")
def library_list() -> dict[str, Any]:
    return {"items": library.list_saved()}


@app.get("/library/{item_id}")
def library_get(item_id: str) -> dict[str, Any]:
    item = library.get_saved(item_id)
    return item or {"error": "not found"}


@app.post("/library")
def library_save(req: SaveRequest) -> dict[str, Any]:
    try:
        GraphDocument.model_validate(req.graph)
    except Exception as e:  # noqa: BLE001
        return {"error": f"invalid graph: {e}"}
    return library.save(req.title, req.sop_text, req.graph)


@app.delete("/library/{item_id}")
def library_delete(item_id: str) -> dict[str, Any]:
    return {"deleted": library.delete(item_id)}
