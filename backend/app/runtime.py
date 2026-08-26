"""Deterministic graph runtime — executes a compiled GraphDocument.

NO LLM at run time. Given a graph and an `entry` input, it:
  1. topologically orders the nodes (Kahn's algorithm),
  2. runs forward: fetch -> call tool, decision -> evaluate + prune branches,
     action -> call tool,
  3. produces an execution TRACE (what ran, what was skipped, and why).

Because the skip set is a pure function of the decision outputs (which are pure
functions of the input data + deterministic tools), the whole run is reproducible.

The condition evaluator is a SAFE mini-interpreter built on Python's `ast`. It only
permits boolean/comparison/arithmetic ops, names, attribute/index access and literals
— never function calls, imports, or arbitrary code. This is both a safety guardrail
and a good talking point.
"""
from __future__ import annotations

import ast
import operator
from typing import Any

from app.graph_schema import GraphDocument, Node
from app.tools import TOOL_REGISTRY


# ─────────────────────────────────────────────────────────────────────────────
# Safe condition evaluation
# ─────────────────────────────────────────────────────────────────────────────
_ALLOWED_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_ALLOWED_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


class ConditionError(ValueError):
    """Raised when a decision condition is invalid or references unknown data."""


def safe_eval_condition(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a boolean expression against `context` (node_id -> output dict).

    Supports: and/or/not, comparisons, +,-,*,/, names, attribute access
    (node.field), subscript (node['field']), and literals. Nothing else.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:  # noqa: PERF203
        raise ConditionError(f"invalid condition syntax: {expr!r} ({e})") from e

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.BoolOp):
            values = [_eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            return any(values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _eval(node.operand)
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                op_fn = _ALLOWED_CMP.get(type(op))
                if op_fn is None:
                    raise ConditionError(f"operator not allowed: {type(op).__name__}")
                right = _eval(comparator)
                if not op_fn(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BinOp):
            op_fn = _ALLOWED_BIN.get(type(node.op))
            if op_fn is None:
                raise ConditionError(f"operator not allowed: {type(node.op).__name__}")
            return op_fn(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.Name):
            if node.id not in context:
                # allow bare true/false/none written as names, defensively
                low = node.id.lower()
                if low == "true":
                    return True
                if low == "false":
                    return False
                if low == "none":
                    return None
                raise ConditionError(f"unknown reference: {node.id}")
            return context[node.id]
        if isinstance(node, ast.Attribute):
            base = _eval(node.value)
            if isinstance(base, dict) and node.attr in base:
                return base[node.attr]
            raise ConditionError(f"field not found: {node.attr}")
        if isinstance(node, ast.Subscript):
            base = _eval(node.value)
            key = _eval(node.slice)
            try:
                return base[key]
            except Exception as e:  # noqa: BLE001
                raise ConditionError(f"cannot index {key!r}") from e
        if isinstance(node, ast.Constant):
            return node.value
        raise ConditionError(f"expression element not allowed: {type(node).__name__}")

    result = _eval(tree)
    return bool(result)


# ─────────────────────────────────────────────────────────────────────────────
# Input reference resolution
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_ref(ref: Any, entry: dict[str, Any], outputs: dict[str, Any]) -> Any:
    """Resolve one input binding.

    - {"value": X}         -> literal X
    - "entry.<field>"      -> entry[field]
    - "<node_id>.<field>"  -> outputs[node_id][field]
    - anything else        -> returned as-is (treated as a literal)
    """
    if isinstance(ref, dict) and "value" in ref:
        return ref["value"]
    if isinstance(ref, str) and "." in ref:
        head, field = ref.split(".", 1)
        if head == "entry":
            return entry.get(field)
        if head in outputs and isinstance(outputs[head], dict):
            return outputs[head].get(field)
    return ref


def _resolve_inputs(node: Node, entry: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    return {k: _resolve_ref(v, entry, outputs) for k, v in node.inputs.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Topological ordering
# ─────────────────────────────────────────────────────────────────────────────
def _dependencies(graph: GraphDocument) -> dict[str, set[str]]:
    """Node -> set of node ids it depends on (incoming edges + input references)."""
    deps: dict[str, set[str]] = {n.id: set() for n in graph.nodes}
    for e in graph.edges:
        if e.from_id in deps and e.to_id in deps:
            deps[e.to_id].add(e.from_id)
    for n in graph.nodes:
        for ref in n.inputs.values():
            if isinstance(ref, str) and "." in ref:
                head = ref.split(".", 1)[0]
                if head != "entry" and head in deps:
                    deps[n.id].add(head)
    return deps


def _topo_order(graph: GraphDocument) -> list[str]:
    deps = _dependencies(graph)
    order: list[str] = []
    ready = sorted([n for n, d in deps.items() if not d])
    remaining = {n: set(d) for n, d in deps.items()}
    while ready:
        cur = ready.pop(0)
        order.append(cur)
        for other, d in remaining.items():
            if cur in d:
                d.discard(cur)
                if not d and other not in order and other not in ready:
                    ready.append(other)
        ready.sort()
    if len(order) != len(graph.nodes):
        raise ConditionError("cycle detected in graph — cannot execute")
    return order


# ─────────────────────────────────────────────────────────────────────────────
# The engine
# ─────────────────────────────────────────────────────────────────────────────
def run_graph(graph: GraphDocument, entry: dict[str, Any]) -> dict[str, Any]:
    """Execute the graph and return {outputs, trace, action_log_slice}."""
    order = _topo_order(graph)
    outputs: dict[str, Any] = {}
    cut: set[tuple[str, str]] = set()  # control edges the runtime has pruned
    trace: list[dict[str, Any]] = []

    def _is_live(node_id: str) -> bool:
        incoming = graph.incoming(node_id)
        if not incoming:
            return True  # root node
        # Branch targets: live only if reached via an un-cut branch edge whose
        # source decision already ran.
        branch_edges = [e for e in incoming if e.branch is not None]
        if branch_edges:
            return any(
                e.from_id in outputs and (e.from_id, e.to_id) not in cut
                for e in branch_edges
            )
        # Plain nodes: live if any producer ran via an un-cut edge.
        return any(
            e.from_id in outputs and (e.from_id, e.to_id) not in cut for e in incoming
        )

    for idx, nid in enumerate(order):
        node = graph.node(nid)

        if not _is_live(nid):
            trace.append({"order": idx, "node": nid, "type": node.type,
                          "status": "skipped", "reason": "branch not taken / unreachable"})
            continue

        if node.type == "decision":
            try:
                result = safe_eval_condition(node.condition or "False", outputs)
            except ConditionError as e:
                trace.append({"order": idx, "node": nid, "type": "decision",
                              "status": "error", "reason": str(e)})
                outputs[nid] = {"result": False, "error": str(e)}
                result = False
            else:
                outputs[nid] = {"result": result}
            chosen = "true" if result else "false"
            cut_targets = []
            for e in graph.outgoing(nid):
                if e.branch is not None and e.branch != chosen:
                    cut.add((e.from_id, e.to_id))
                    cut_targets.append(e.to_id)
            trace.append({"order": idx, "node": nid, "type": "decision",
                          "status": "ran", "condition": node.condition,
                          "result": result, "chose": chosen, "pruned": cut_targets})
            continue

        # fetch or action -> call the tool
        tool = TOOL_REGISTRY.get(node.tool or "")
        if tool is None:
            trace.append({"order": idx, "node": nid, "type": node.type,
                          "status": "error", "reason": f"unknown tool: {node.tool}"})
            outputs[nid] = {"error": f"unknown tool: {node.tool}"}
            continue
        resolved = _resolve_inputs(node, entry, outputs)
        try:
            out = tool.fn(**resolved)
        except TypeError as e:
            out = {"error": f"bad inputs for {node.tool}: {e}"}
        outputs[nid] = out
        trace.append({"order": idx, "node": nid, "type": node.type,
                      "status": "ran", "tool": node.tool,
                      "inputs": resolved, "output": out})

    ran = [s["node"] for s in trace if s["status"] == "ran"]
    skipped = [s["node"] for s in trace if s["status"] == "skipped"]
    return {
        "outputs": outputs,
        "trace": trace,
        "summary": {"ran": ran, "skipped": skipped, "order": order},
    }
