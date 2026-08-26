"""Validation guardrail for compiler output.

After the LLM proposes a graph, we do NOT trust it blindly. We check:
  1. it parses into a GraphDocument (schema-valid),
  2. every referenced tool actually exists,
  3. edges reference existing nodes,
  4. every decision node has both a 'true' and a 'false' outgoing branch,
  5. the graph is acyclic (a DAG) — required for deterministic execution.

Returns a list of human-readable problems (empty list == valid).
"""
from __future__ import annotations

from app.graph_schema import GraphDocument
from app.tools import tool_names


def validate_graph(graph: GraphDocument) -> list[str]:
    problems: list[str] = []
    ids = {n.id for n in graph.nodes}
    tools = tool_names()

    if not graph.nodes:
        problems.append("graph has no nodes")

    # duplicate ids
    if len(ids) != len(graph.nodes):
        problems.append("duplicate node ids detected")

    # tool existence
    for n in graph.nodes:
        if n.type in ("fetch", "action") and n.tool not in tools:
            problems.append(f"node '{n.id}' references unknown tool '{n.tool}'")

    # edges reference real nodes
    for e in graph.edges:
        if e.from_id not in ids:
            problems.append(f"edge from unknown node '{e.from_id}'")
        if e.to_id not in ids:
            problems.append(f"edge to unknown node '{e.to_id}'")

    # decisions need both branches
    for n in graph.nodes:
        if n.type == "decision":
            branches = {e.branch for e in graph.outgoing(n.id) if e.branch}
            missing = {"true", "false"} - branches
            if missing:
                problems.append(
                    f"decision '{n.id}' is missing branch(es): {', '.join(sorted(missing))}"
                )

    # acyclic check (DFS)
    if not _is_acyclic(graph):
        problems.append("graph contains a cycle (must be acyclic to run)")

    return problems


def _is_acyclic(graph: GraphDocument) -> bool:
    adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        if e.from_id in adj and e.to_id in adj:
            adj[e.from_id].append(e.to_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                return False  # back edge -> cycle
            if color[v] == WHITE and not dfs(v):
                return False
        color[u] = BLACK
        return True

    return all(color[n] != WHITE or dfs(n) for n in adj)
