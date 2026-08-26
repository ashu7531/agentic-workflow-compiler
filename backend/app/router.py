"""Router — decides how to handle an incoming case: existing workflow vs agent.

Policy: "match an existing workflow first, agent-fallback."
  1. Figure out the case's intent/domain.
  2. SEARCH the saved workflow library for one that matches that domain.
     - match found  -> run that saved workflow deterministically (fast, auditable).
     - no saved match, but the domain is one we can compile -> compile & run it.
  3. Nothing matches -> hand the case to the tool-using agent.

This router lives in OUR platform (not the client's code) — routing is core
intelligence, so the client only forwards cases and registers tools.
"""
from __future__ import annotations

from typing import Any

from app import library
from app.agent import detect_domain, run_agent
from app.compiler import compile_sop
from app.graph_schema import GraphDocument
from app.runtime import run_graph
from app.tools import ACTION_LOG, set_case
from app.validator import validate_graph


def _run_graph_dict(graph_dict: dict[str, Any], entry: dict[str, Any],
                    case: dict[str, Any]) -> dict[str, Any]:
    graph = GraphDocument.model_validate(graph_dict)
    ACTION_LOG.clear()
    set_case(case)
    run = run_graph(graph, entry)
    run["action_log"] = list(ACTION_LOG)
    return run


def _match_saved_workflow(case_text: str) -> dict[str, Any] | None:
    """Search the saved library for a workflow whose domain matches the case."""
    domain = detect_domain(case_text)
    if domain is None:
        return None
    for wf in library.all_full():
        if detect_domain(wf.get("sop_text", "")) == domain and wf.get("graph"):
            return wf
    return None


def _builtin_sop_for_domain(domain: str) -> str | None:
    """The built-in example SOP text for a recognized domain (a full procedure,
    which compiles into a proper workflow — unlike a short case description)."""
    for s in library.SAMPLE_SOPS:
        if detect_domain(s.get("sop_text", "")) == domain:
            return s["sop_text"]
    return None


def handle_case(case_text: str, entry: dict[str, Any] | None = None,
                case: dict[str, Any] | None = None, force_agent: bool = False) -> dict[str, Any]:
    entry = entry or {}
    case = case or {}

    if force_agent:
        agent = run_agent(case_text, entry, case, policy_text=case_text)
        return {"route": "agent", "reason": "forced agent mode", "agent": agent}

    # 1. Search the saved library for a matching workflow.
    saved = _match_saved_workflow(case_text)
    if saved is not None:
        run = _run_graph_dict(saved["graph"], entry, case)
        return {"route": "workflow",
                "reason": f"matched saved workflow “{saved['title']}”",
                "matched_title": saved["title"], "graph": saved["graph"], "run": run}

    # 2. No saved match — if we recognize the domain, build a workflow from that
    #    domain's built-in SOP (a full procedure, not the short case text).
    domain = detect_domain(case_text)
    sop_text = _builtin_sop_for_domain(domain) if domain else None
    if sop_text:
        result = compile_sop(sop_text)
        if result.kind == "graph" and result.graph is not None and not validate_graph(result.graph):
            graph_dict = result.graph.model_dump(by_alias=True)
            run = _run_graph_dict(graph_dict, entry, case)
            return {"route": "workflow",
                    "reason": f"no saved workflow — built a {domain} workflow from the built-in SOP",
                    "matched_title": result.graph.sop_title, "graph": graph_dict, "run": run}

    # 3. Nothing matched — the agent handles it.
    agent = run_agent(case_text, entry, case, policy_text=case_text)
    return {"route": "agent",
            "reason": "no matching workflow — handled by the agent", "agent": agent}
