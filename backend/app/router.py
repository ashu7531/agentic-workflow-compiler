"""Router — decides how to handle an incoming case: deterministic workflow vs agent.

Policy: "workflow-first, agent-fallback."
  1. Try to compile the case's procedure into a workflow.
  2. If we get a valid workflow  -> run it deterministically (fast, auditable).
  3. If we can't (unknown domain / the compiler asks for clarification) -> hand to
     the tool-using agent.

This router lives in OUR platform (not the client's code) — routing is core
intelligence, so the client only forwards cases and registers tools.
"""
from __future__ import annotations

from typing import Any

from app.agent import run_agent
from app.compiler import compile_sop
from app.runtime import run_graph
from app.validator import validate_graph


def handle_case(case_text: str, entry: dict[str, Any] | None = None,
                case: dict[str, Any] | None = None, force_agent: bool = False) -> dict[str, Any]:
    entry = entry or {}
    case = case or {}

    if force_agent:
        agent = run_agent(case_text, entry, case, policy_text=case_text)
        return {"route": "agent", "reason": "forced agent mode", "agent": agent}

    # 1. Try to compile a workflow for this case.
    result = compile_sop(case_text)
    if result.kind == "graph" and result.graph is not None:
        problems = validate_graph(result.graph)
        if not problems:
            # 2. Deterministic workflow path.
            from app.tools import ACTION_LOG, set_case
            ACTION_LOG.clear()
            set_case(case)
            run = run_graph(result.graph, entry)
            run["action_log"] = list(ACTION_LOG)
            return {"route": "workflow", "reason": "matched a compilable workflow",
                    "graph": result.graph.model_dump(by_alias=True), "run": run}

    # 3. No usable workflow -> agent fallback.
    agent = run_agent(case_text, entry, case, policy_text=case_text)
    return {"route": "agent",
            "reason": "no matching workflow — handled by the agent", "agent": agent}
