"""Agent Mode — a real tool-calling loop (ReAct-style) for messy / unknown cases.

Difference from the deterministic runtime:
  - The runtime executes a FIXED compiled graph (no LLM at run time).
  - The AGENT is given a goal + the SOP/policy text + the toolbox, and it decides
    each next action ITSELF, in a loop: think -> call a tool -> observe -> think …
    until it resolves the case (or escalates). Many LLM calls, autonomous, adaptive.

Two backends:
  - Gemini mode (GEMINI_API_KEY set): a genuine ReAct loop via structured JSON actions.
  - Mock mode (no key): a deterministic, domain-aware scripted loop so the feature is
    fully demoable without a key. Clearly labelled as mock.
"""
from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.tools import ACTION_LOG, TOOL_REGISTRY, set_case, tool_catalog_text

MAX_STEPS = 8


# ─────────────────────────────────────────────────────────────────────────────
# Domain detection (shared idea with the compiler) — used by the mock agent and
# by the router to recognise which domain a free-text case belongs to.
# ─────────────────────────────────────────────────────────────────────────────
def detect_domain(text: str) -> str | None:
    low = (text or "").lower()
    if "refund" in low:
        return "refund"
    if any(k in low for k in ("toxic", "moderat", "reported", "content")):
        return "moderation"
    if any(k in low for k in ("alert", "incident", "severity", "on-call", "on call", "paged")):
        return "incident"
    if any(k in low for k in ("payment", "subscription", "dunning", "trial", "billing")):
        return "saas"
    if any(k in low for k in ("delay", "deliver", "pickup", "shipment", "order")):
        return "delivery"
    return None


def run_agent(case_text: str, entry: dict[str, Any] | None = None,
              case: dict[str, Any] | None = None, policy_text: str = "") -> dict[str, Any]:
    """Resolve a single case with a tool-using agent. Returns steps + final answer."""
    ACTION_LOG.clear()
    set_case(case or {})
    entry = entry or {}
    settings = get_settings()
    if settings.has_llm:
        result = _gemini_agent(case_text, entry, policy_text)
    else:
        result = _mock_agent(case_text, entry)
    result["action_log"] = list(ACTION_LOG)
    result["mode"] = "gemini" if settings.has_llm else "mock"
    return result


def _call_tool(name: str, args: dict[str, Any], entry: dict[str, Any]) -> Any:
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return {"error": f"unknown tool: {name}"}
    # Fill any missing id-like params from entry (best-effort).
    call_args = dict(args or {})
    for pname in tool.params:
        if pname not in call_args and pname in entry:
            call_args[pname] = entry[pname]
    # Also map the single entry value to the tool's id param if not provided.
    if entry and not call_args:
        first_val = next(iter(entry.values()), "")
        for pname in tool.params:
            if pname not in call_args:
                call_args[pname] = first_val
                break
    try:
        return tool.fn(**call_args)
    except TypeError as e:
        return {"error": f"bad args for {name}: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Gemini ReAct loop
# ─────────────────────────────────────────────────────────────────────────────
def _gemini_agent(case_text: str, entry: dict[str, Any], policy_text: str) -> dict[str, Any]:
    from google import genai

    settings = get_settings()
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    system = (
        "You are an operations agent resolving ONE support case. Work step by step.\n"
        "You may ONLY use the tools listed below. Follow the POLICY if provided.\n\n"
        f"TOOLS:\n{tool_catalog_text()}\n\n"
        f"POLICY / SOP (guidance):\n{policy_text or '(none provided — use good judgment; escalate if unsure)'}\n\n"
        f"CASE INPUT (ids): {json.dumps(entry)}\n\n"
        "On EACH turn reply with ONE JSON object only, no prose, no markdown:\n"
        '  {\"thought\": \"...\", \"action\": \"tool\", \"tool\": \"<name>\", \"args\": { }}\n'
        "OR, when the case is resolved:\n"
        '  {\"thought\": \"...\", \"action\": \"final\", \"final\": \"<summary of what you did>\"}\n'
        "Prefer to gather needed data with fetch tools first, then take exactly the "
        "actions the policy requires. If you cannot proceed safely, take the escalate/"
        "notify-a-human tool or finish with a final that says you are escalating."
    )

    transcript: list[str] = [f"CASE: {case_text}"]
    steps: list[dict[str, Any]] = []

    for _ in range(MAX_STEPS):
        prompt = system + "\n\nHISTORY:\n" + "\n".join(transcript) + "\n\nYour next JSON:"
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        raw = (resp.text or "").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            steps.append({"thought": "(could not parse model output)", "raw": raw[:300]})
            break

        thought = data.get("thought", "")
        if data.get("action") == "final":
            steps.append({"thought": thought, "final": data.get("final", "")})
            return {"steps": steps, "final": data.get("final", "")}

        tool = data.get("tool", "")
        args = data.get("args", {}) or {}
        observation = _call_tool(tool, args, entry)
        steps.append({"thought": thought, "tool": tool, "args": args, "observation": observation})
        transcript.append(f"THOUGHT: {thought}")
        transcript.append(f"ACTION: {tool}({json.dumps(args)}) -> {json.dumps(observation, default=str)}")

    return {"steps": steps, "final": "Reached step limit without a final answer — escalating to a human."}


# ─────────────────────────────────────────────────────────────────────────────
# Mock agent (no key) — deterministic, domain-aware scripted loop for demos
# ─────────────────────────────────────────────────────────────────────────────
def _mock_agent(case_text: str, entry: dict[str, Any]) -> dict[str, Any]:
    domain = detect_domain(case_text)
    steps: list[dict[str, Any]] = []

    def do(thought: str, tool: str, args: dict[str, Any] | None = None):
        obs = _call_tool(tool, args or {}, entry)
        steps.append({"thought": thought, "tool": tool, "args": args or {}, "observation": obs})
        return obs

    if domain == "delivery":
        c = do("First I'll check how many times the customer has complained.", "get_complaint_count")
        if (c.get("count") or 0) >= 2:
            do("They've complained repeatedly — escalating to a manager.", "escalate_to_manager")
            final = "Escalated to a manager due to repeat complaints."
        else:
            t = do("Let me check the shipment's tracking status.", "get_tracking")
            f = do("Now checking whether the facility is overloaded.", "get_facility_status")
            if (t.get("days_late") or 0) > 3 and f.get("overloaded"):
                do("Delayed and the hub is overloaded — I'll notify the customer.", "send_notification")
                final = "Notified the customer about the delay."
            else:
                do("Not a hub-overload delay — I'll reschedule the delivery.", "reschedule_delivery")
                final = "Rescheduled the delivery."
    elif domain == "refund":
        o = do("Let me look up the order status and amount.", "get_order_status")
        if (o.get("amount") or 0) > 5000:
            do("High-value refund — escalating to a manager.", "escalate_to_manager")
            final = "Escalated the high-value refund to a manager."
        elif o.get("delivered") and (o.get("days_since_delivery") or 99) <= 7:
            do("Delivered and within the return window — approving.", "approve_refund")
            final = "Approved the refund."
        else:
            do("Outside the return window — rejecting.", "reject_refund")
            final = "Rejected the refund."
    elif domain == "moderation":
        r = do("Let me pull the report's toxicity score and prior violations.", "get_report")
        if (r.get("prior_violations") or 0) >= 3:
            do("User is a repeat offender — suspending the account.", "suspend_account")
            final = "Suspended the account (repeat violations)."
        elif (r.get("toxicity_score") or 0) > 0.9:
            do("Very high toxicity — removing immediately.", "remove_content")
            final = "Removed the content."
        elif (r.get("toxicity_score") or 0) >= 0.6:
            do("Borderline — sending to a human moderator.", "send_to_moderator")
            final = "Sent to a human moderator."
        else:
            do("Low toxicity — dismissing the report.", "dismiss_report")
            final = "Dismissed the report."
    elif domain == "incident":
        a = do("Let me check the alert's severity.", "get_alert")
        if str(a.get("severity")).lower() == "critical":
            do("Critical — paging the on-call engineer.", "page_oncall")
            final = "Paged the on-call engineer."
        else:
            do("Not critical — logging a ticket.", "log_ticket")
            final = "Logged a ticket."
    elif domain == "saas":
        s = do("Let me fetch the subscription's trial flag and failure count.", "get_subscription")
        if s.get("on_trial"):
            do("It's a trial — cancelling the trial.", "cancel_trial")
            final = "Cancelled the trial."
        elif (s.get("failure_count") or 0) >= 3:
            do("Payment failed repeatedly — pausing the subscription.", "pause_subscription")
            final = "Paused the subscription."
        else:
            do("Emailing the customer a payment-update link.", "email_customer")
            final = "Emailed a payment link."
    else:
        steps.append({"thought": "I don't have tools or a policy for this kind of case.",
                      "final": "No matching tools/policy — escalating to a human."})
        final = "No matching tools/policy — escalating to a human."

    return {"steps": steps, "final": final}
