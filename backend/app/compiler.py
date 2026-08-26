"""The COMPILER — turns a plain-English SOP into a decision graph.

This is the one place AI is genuinely required. It:
  1. builds a prompt (schema + tool catalog + few-shot examples + rules),
  2. asks Gemini for JSON that is EITHER a graph OR clarifying questions,
  3. parses/validates the result.

If no GEMINI_API_KEY is configured, it falls back to a deterministic MOCK compiler
so the app is fully runnable before a key is added. The mock returns the canonical
"delivery delay" graph, and asks a clarifying question for very short/vague SOPs —
so both the happy path and the clarification path can be demoed with no key.
"""
from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.graph_schema import GraphDocument
from app.tools import tool_catalog_text

# ── The output contract we ask the LLM to follow ──
_SCHEMA_HINT = """
Return a SINGLE JSON object, and nothing else. It must be ONE of:

A) A compiled graph:
{
  "type": "graph",
  "sop_title": "<short title>",
  "entry_fields": ["wbn"],                 // inputs the workflow needs at run time
  "nodes": [
    {"id": "fetch_tracking", "type": "fetch", "tool": "get_tracking",
     "inputs": {"wbn": "entry.wbn"}, "label": "Get tracking"},
    {"id": "decide_delay", "type": "decision",
     "condition": "fetch_tracking.days_late > 3 and fetch_facility.overloaded == True",
     "label": "Delayed & overloaded?"},
    {"id": "notify", "type": "action", "tool": "send_notification",
     "inputs": {"wbn": "entry.wbn", "channel": "email"}, "label": "Notify customer"}
  ],
  "edges": [
    {"from": "fetch_tracking", "to": "decide_delay"},
    {"from": "decide_delay", "to": "notify", "branch": "true"},
    {"from": "decide_delay", "to": "reschedule", "branch": "false"}
  ]
}

B) Clarifying questions (use ONLY when the SOP is missing information you need):
{ "type": "clarification", "needs_clarification": ["Notify by email or SMS?"] }

RULES:
- Node types are exactly: "fetch" (calls a tool to read data), "decision" (pure
  boolean logic over already-fetched data, NO tool), "action" (calls a tool to do
  something).
- Only use tools from the provided tool catalog. Never invent tools.
- Every decision node MUST have exactly one "true" and one "false" outgoing edge.
- Decision conditions may reference earlier node outputs as "<node_id>.<field>".
- Input bindings use "entry.<field>" for run inputs or "<node_id>.<field>" for
  earlier outputs.
- The graph must be acyclic (no loops).
- Do NOT wrap the JSON in markdown fences.
"""


def _build_prompt(sop_text: str, answers: dict[str, str] | None) -> str:
    answer_block = ""
    if answers:
        joined = "\n".join(f"- {q}: {a}" for q, a in answers.items())
        answer_block = f"\nThe user answered earlier clarifying questions:\n{joined}\n"
    return (
        "You compile Standard Operating Procedures (SOPs) written in plain English "
        "into an executable decision graph.\n\n"
        f"AVAILABLE TOOLS:\n{tool_catalog_text()}\n\n"
        f"OUTPUT FORMAT:\n{_SCHEMA_HINT}\n"
        f"{answer_block}\n"
        f"SOP TO COMPILE:\n\"\"\"\n{sop_text.strip()}\n\"\"\"\n"
    )


class CompileResult:
    """Either a graph or clarifying questions."""

    def __init__(self, kind: str, graph: GraphDocument | None = None,
                 questions: list[str] | None = None, raw: str = ""):
        self.kind = kind  # "graph" | "clarification"
        self.graph = graph
        self.questions = questions or []
        self.raw = raw

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "graph" and self.graph is not None:
            return {"type": "graph", "graph": self.graph.model_dump(by_alias=True)}
        return {"type": "clarification", "needs_clarification": self.questions}


def compile_sop(sop_text: str, answers: dict[str, str] | None = None) -> CompileResult:
    settings = get_settings()
    if not settings.has_llm:
        return _mock_compile(sop_text, answers)
    return _gemini_compile(sop_text, answers)


# ─────────────────────────────────────────────────────────────────────────────
# Real compiler (Gemini)
# ─────────────────────────────────────────────────────────────────────────────
def _gemini_compile(sop_text: str, answers: dict[str, str] | None) -> CompileResult:
    from google import genai  # imported lazily so the app runs without the package

    settings = get_settings()
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = _build_prompt(sop_text, answers)

    resp = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0},
    )
    raw = (resp.text or "").strip()
    return _parse_compiler_output(raw)


def _parse_compiler_output(raw: str) -> CompileResult:
    # be tolerant of accidental markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"compiler returned non-JSON output: {e}\n---\n{raw[:500]}") from e

    if data.get("type") == "clarification":
        return CompileResult("clarification",
                             questions=data.get("needs_clarification", []), raw=raw)

    # graph — accept either {type:graph, ...fields} or nested {graph: {...}}
    graph_payload = data.get("graph", data)
    graph_payload.pop("type", None)
    graph = GraphDocument.model_validate(graph_payload)
    return CompileResult("graph", graph=graph, raw=raw)


# ─────────────────────────────────────────────────────────────────────────────
# Mock compiler (no API key) — deterministic, for local dev/demo
# ─────────────────────────────────────────────────────────────────────────────
def _mock_compile(sop_text: str, answers: dict[str, str] | None) -> CompileResult:
    # Demo the clarification path for very short/vague SOPs (unless already answered).
    if len(sop_text.split()) < 6 and not answers:
        return CompileResult(
            "clarification",
            questions=[
                "What condition should trigger an action (e.g. days late)?",
                "What action should be taken, and via which channel (email/SMS)?",
            ],
        )

    # Canned workflows per domain so variety works in mock mode (no key).
    low = sop_text.lower()
    if "refund" in low:
        return CompileResult("graph", graph=_mock_refund_graph())
    if any(k in low for k in ("toxic", "moderat", "reported", "content")):
        return CompileResult("graph", graph=_mock_moderation_graph())
    if any(k in low for k in ("alert", "incident", "severity", "on-call", "on call", "paged")):
        return CompileResult("graph", graph=_mock_incident_graph())
    if any(k in low for k in ("payment", "subscription", "dunning", "trial", "billing")):
        return CompileResult("graph", graph=_mock_saas_graph())
    if not any(k in low for k in ("delay", "deliver", "pickup")):
        # No key + no known domain keyword: be honest rather than guessing.
        return CompileResult("clarification", questions=[
            "Mock mode (no API key) supports these example domains only: delivery/pickup "
            "delay, refund, content moderation, IT incident, and SaaS payment. Add a "
            "GEMINI_API_KEY to compile any procedure — or reword using one of these domains.",
        ])

    channel = "email"
    if answers:
        for q, a in answers.items():
            if "sms" in a.lower():
                channel = "sms"

    graph = GraphDocument.model_validate({
        "sop_title": "Delivery Delay Handling",
        "entry_fields": ["wbn"],
        "nodes": [
            {"id": "fetch_tracking", "type": "fetch", "tool": "get_tracking",
             "inputs": {"wbn": "entry.wbn"}, "label": "Get tracking"},
            {"id": "fetch_facility", "type": "fetch", "tool": "get_facility_status",
             "inputs": {}, "label": "Get facility load"},
            {"id": "fetch_complaints", "type": "fetch", "tool": "get_complaint_count",
             "inputs": {"wbn": "entry.wbn"}, "label": "Get complaint count"},
            {"id": "decide_escalate", "type": "decision",
             "condition": "fetch_complaints.count >= 2",
             "label": "Complained twice?"},
            {"id": "escalate", "type": "action", "tool": "escalate_to_manager",
             "inputs": {"wbn": "entry.wbn"}, "label": "Escalate to manager"},
            {"id": "decide_delay", "type": "decision",
             "condition": "fetch_tracking.days_late > 3 and fetch_facility.overloaded == True",
             "label": "Delayed >3d & overloaded?"},
            {"id": "notify", "type": "action", "tool": "send_notification",
             "inputs": {"wbn": "entry.wbn", "channel": channel}, "label": "Notify customer"},
            {"id": "reschedule", "type": "action", "tool": "reschedule_delivery",
             "inputs": {"wbn": "entry.wbn"}, "label": "Reschedule delivery"},
        ],
        "edges": [
            # Linear spine so the escalate=true branch cleanly skips the whole
            # delay-check subtree (no node ends up referencing skipped data).
            {"from": "fetch_complaints", "to": "decide_escalate"},
            {"from": "decide_escalate", "to": "escalate", "branch": "true"},
            {"from": "decide_escalate", "to": "fetch_tracking", "branch": "false"},
            {"from": "fetch_tracking", "to": "fetch_facility"},
            {"from": "fetch_facility", "to": "decide_delay"},
            {"from": "decide_delay", "to": "notify", "branch": "true"},
            {"from": "decide_delay", "to": "reschedule", "branch": "false"},
        ],
    })
    return CompileResult("graph", graph=graph)


def _mock_refund_graph() -> GraphDocument:
    return GraphDocument.model_validate({
        "sop_title": "Refund Request Handling",
        "entry_fields": ["wbn"],
        "nodes": [
            {"id": "fetch_order", "type": "fetch", "tool": "get_order_status",
             "inputs": {"wbn": "entry.wbn"}, "label": "Get order status"},
            {"id": "decide_amount", "type": "decision",
             "condition": "fetch_order.amount > 5000", "label": "Amount over 5000?"},
            {"id": "escalate", "type": "action", "tool": "escalate_to_manager",
             "inputs": {"wbn": "entry.wbn"}, "label": "Escalate to manager"},
            {"id": "decide_window", "type": "decision",
             "condition": "fetch_order.delivered == True and fetch_order.days_since_delivery <= 7",
             "label": "Delivered & within 7 days?"},
            {"id": "approve", "type": "action", "tool": "approve_refund",
             "inputs": {"wbn": "entry.wbn"}, "label": "Approve refund"},
            {"id": "reject", "type": "action", "tool": "reject_refund",
             "inputs": {"wbn": "entry.wbn"}, "label": "Reject refund"},
        ],
        "edges": [
            {"from": "fetch_order", "to": "decide_amount"},
            {"from": "decide_amount", "to": "escalate", "branch": "true"},
            {"from": "decide_amount", "to": "decide_window", "branch": "false"},
            {"from": "decide_window", "to": "approve", "branch": "true"},
            {"from": "decide_window", "to": "reject", "branch": "false"},
        ],
    })


def _mock_moderation_graph() -> GraphDocument:
    """Content-moderation workflow (a different domain, uses moderation tools)."""
    return GraphDocument.model_validate({
        "sop_title": "Content Moderation",
        "entry_fields": ["content_id"],
        "nodes": [
            {"id": "fetch_report", "type": "fetch", "tool": "get_report",
             "inputs": {"content_id": "entry.content_id"}, "label": "Get report data"},
            {"id": "decide_suspend", "type": "decision",
             "condition": "fetch_report.prior_violations >= 3", "label": "3+ prior violations?"},
            {"id": "suspend", "type": "action", "tool": "suspend_account",
             "inputs": {"content_id": "entry.content_id"}, "label": "Suspend account"},
            {"id": "decide_remove", "type": "decision",
             "condition": "fetch_report.toxicity_score > 0.9", "label": "Toxicity > 0.9?"},
            {"id": "remove", "type": "action", "tool": "remove_content",
             "inputs": {"content_id": "entry.content_id"}, "label": "Remove content"},
            {"id": "decide_review", "type": "decision",
             "condition": "fetch_report.toxicity_score >= 0.6", "label": "Toxicity 0.6–0.9?"},
            {"id": "moderator", "type": "action", "tool": "send_to_moderator",
             "inputs": {"content_id": "entry.content_id"}, "label": "Send to moderator"},
            {"id": "dismiss", "type": "action", "tool": "dismiss_report",
             "inputs": {"content_id": "entry.content_id"}, "label": "Dismiss report"},
        ],
        "edges": [
            {"from": "fetch_report", "to": "decide_suspend"},
            {"from": "decide_suspend", "to": "suspend", "branch": "true"},
            {"from": "decide_suspend", "to": "decide_remove", "branch": "false"},
            {"from": "decide_remove", "to": "remove", "branch": "true"},
            {"from": "decide_remove", "to": "decide_review", "branch": "false"},
            {"from": "decide_review", "to": "moderator", "branch": "true"},
            {"from": "decide_review", "to": "dismiss", "branch": "false"},
        ],
    })


def _mock_incident_graph() -> GraphDocument:
    """IT incident response (SHORT — a single decision)."""
    return GraphDocument.model_validate({
        "sop_title": "IT Incident Response",
        "entry_fields": ["alert_id"],
        "nodes": [
            {"id": "fetch_alert", "type": "fetch", "tool": "get_alert",
             "inputs": {"alert_id": "entry.alert_id"}, "label": "Get alert"},
            {"id": "decide_critical", "type": "decision",
             "condition": "fetch_alert.severity == 'critical'", "label": "Critical severity?"},
            {"id": "page", "type": "action", "tool": "page_oncall",
             "inputs": {"alert_id": "entry.alert_id"}, "label": "Page on-call engineer"},
            {"id": "ticket", "type": "action", "tool": "log_ticket",
             "inputs": {"alert_id": "entry.alert_id"}, "label": "Log a ticket"},
        ],
        "edges": [
            {"from": "fetch_alert", "to": "decide_critical"},
            {"from": "decide_critical", "to": "page", "branch": "true"},
            {"from": "decide_critical", "to": "ticket", "branch": "false"},
        ],
    })


def _mock_saas_graph() -> GraphDocument:
    """SaaS failed-payment handling (MEDIUM — two decisions)."""
    return GraphDocument.model_validate({
        "sop_title": "SaaS Payment Failure",
        "entry_fields": ["subscription_id"],
        "nodes": [
            {"id": "fetch_sub", "type": "fetch", "tool": "get_subscription",
             "inputs": {"subscription_id": "entry.subscription_id"}, "label": "Get subscription"},
            {"id": "decide_trial", "type": "decision",
             "condition": "fetch_sub.on_trial == True", "label": "On a trial?"},
            {"id": "cancel", "type": "action", "tool": "cancel_trial",
             "inputs": {"subscription_id": "entry.subscription_id"}, "label": "Cancel trial"},
            {"id": "decide_failures", "type": "decision",
             "condition": "fetch_sub.failure_count >= 3", "label": "Failed 3+ times?"},
            {"id": "pause", "type": "action", "tool": "pause_subscription",
             "inputs": {"subscription_id": "entry.subscription_id"}, "label": "Pause subscription"},
            {"id": "email", "type": "action", "tool": "email_customer",
             "inputs": {"subscription_id": "entry.subscription_id"}, "label": "Email payment link"},
        ],
        "edges": [
            {"from": "fetch_sub", "to": "decide_trial"},
            {"from": "decide_trial", "to": "cancel", "branch": "true"},
            {"from": "decide_trial", "to": "decide_failures", "branch": "false"},
            {"from": "decide_failures", "to": "pause", "branch": "true"},
            {"from": "decide_failures", "to": "email", "branch": "false"},
        ],
    })
