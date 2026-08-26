"""The decision-graph data model (the contract between compiler, runtime, and UI).

A compiled SOP is a GraphDocument = a set of typed Nodes connected by Edges.
Kept deliberately small for v1: three node types (fetch / decision / action),
sequential + if/else control flow only. No parallelism or loops.

These Pydantic models are the single source of truth:
- the COMPILER must produce JSON that parses into a GraphDocument,
- the RUNTIME executes a GraphDocument,
- the FRONTEND renders one.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Node types supported in v1.
NodeType = Literal["fetch", "decision", "action"]


class Node(BaseModel):
    """A single step in the workflow.

    fetch    -> reads information by calling a tool (e.g. get_tracking).
    decision -> pure logic; evaluates `condition` and picks a branch. NO tool call.
    action   -> performs an outcome by calling a tool (e.g. send_notification).
    """

    id: str = Field(..., description="Unique node id, e.g. 'fetch_tracking'.")
    type: NodeType

    # For fetch/action nodes: which tool to call and how to fill its inputs.
    # `inputs` maps a tool-parameter name -> a reference string. A reference is
    # either "entry.<field>" (a value from the run input) or "<node_id>.<field>"
    # (a value produced by an earlier node), or a literal wrapped as {"value": X}.
    tool: Optional[str] = Field(
        default=None, description="Tool name for fetch/action nodes."
    )
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="Tool input bindings (references or literals)."
    )

    # For decision nodes: a boolean expression over already-fetched data.
    # e.g. "fetch_tracking.days_late > 3 and fetch_facility.overloaded == True"
    condition: Optional[str] = Field(
        default=None, description="Boolean expression for decision nodes."
    )

    # Free-text label for the UI (optional).
    label: Optional[str] = None

    @model_validator(mode="after")
    def _check_shape(self) -> "Node":
        if self.type in ("fetch", "action") and not self.tool:
            raise ValueError(f"node '{self.id}' of type '{self.type}' requires a 'tool'")
        if self.type == "decision" and not self.condition:
            raise ValueError(f"decision node '{self.id}' requires a 'condition'")
        return self


class Edge(BaseModel):
    """A directed connection between two nodes.

    For edges leaving a DECISION node, `branch` must be "true" or "false" and tells
    the runtime which outcome of the condition this edge represents. For all other
    edges `branch` is None (plain sequential/data flow).
    """

    from_id: str = Field(..., alias="from")
    to_id: str = Field(..., alias="to")
    branch: Optional[Literal["true", "false"]] = None

    model_config = {"populate_by_name": True}


class GraphDocument(BaseModel):
    """A full compiled SOP: metadata + nodes + edges."""

    sop_title: str = Field(default="Untitled SOP")
    entry_fields: list[str] = Field(
        default_factory=list,
        description="Input fields the workflow expects at run time, e.g. ['wbn'].",
    )
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    # ---- convenience lookups ----
    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"node not found: {node_id}")

    def has_node(self, node_id: str) -> bool:
        return any(n.id == node_id for n in self.nodes)

    def incoming(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.to_id == node_id]

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.from_id == node_id]


class ClarificationResponse(BaseModel):
    """What the compiler returns when the SOP is too vague to compile."""

    needs_clarification: list[str] = Field(
        ..., description="Questions the user must answer before compiling."
    )
