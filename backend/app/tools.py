"""Mock tools — the "hands" of the workflow.

In production these would call real APIs (or MCP-exposed tools). Here they are
mocked so the whole app runs standalone with no external systems. Each tool has:
  - a name (referenced by graph nodes),
  - a human description (fed to the compiler so the LLM knows what exists),
  - a callable that returns a plain dict.

The runtime looks tools up in TOOL_REGISTRY by name and calls them with the
node's resolved inputs. Keep tools DETERMINISTIC (fixed outputs) so runs are
reproducible — that's what makes the "deterministic execution" guarantee hold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., dict[str, Any]]
    # Which inputs this tool expects (name -> short description). Used by the
    # compiler prompt and by validation.
    params: dict[str, str]
    # Which CASE fields this (fetch) tool reads. Lets the UI show only the
    # case inputs relevant to the currently loaded workflow.
    case_fields: list[str] = field(default_factory=list)


# --- Mock action log (so the UI/trace can show what "happened") ---
ACTION_LOG: list[str] = []

# --- Per-run CASE data (the facts about the specific case being run) ---
# The UI sends these so you can drive DIFFERENT decision paths. Each fetch tool
# reads its values from CASE, falling back to a sensible default. This is what
# lets you test every branch of a workflow.
CASE: dict[str, Any] = {}

# The editable fields a case can contain, with defaults — also used by the UI
# to prefill the "Case data" editor.
CASE_DEFAULTS: dict[str, Any] = {
    "days_late": 5,          # get_tracking
    "overloaded": True,      # get_facility_status
    "complaint_count": 1,    # get_complaint_count
    "delivered": True,       # get_order_status
    "days_since_delivery": 3,  # get_order_status
    "amount": 6000,          # get_order_status
    "toxicity_score": 0.95,  # get_report (content moderation)
    "prior_violations": 0,   # get_report (content moderation)
    "severity": "critical",  # get_alert (IT incident)
    "on_trial": False,       # get_subscription (SaaS)
    "failure_count": 3,      # get_subscription (SaaS)
}


def set_case(data: dict[str, Any] | None) -> None:
    """Set the case facts for the next run (called by the /run endpoint)."""
    global CASE
    CASE = dict(data or {})


def _c(key: str) -> Any:
    """Read a case fact, falling back to its default."""
    return CASE.get(key, CASE_DEFAULTS.get(key))


def _log(msg: str) -> dict[str, Any]:
    ACTION_LOG.append(msg)
    return {"ok": True, "message": msg}


# --- fetch tools (read data — driven by the CASE so you can test any branch) ---
def get_tracking(wbn: str = "") -> dict[str, Any]:
    """Return mock shipment tracking for a waybill."""
    return {"wbn": wbn, "days_late": _c("days_late"), "status": "In Transit", "city": "Bangalore"}


def get_facility_status() -> dict[str, Any]:
    """Return mock facility load status."""
    return {"overloaded": _c("overloaded"), "facility": "Bangalore South Hub"}


def get_complaint_count(wbn: str = "") -> dict[str, Any]:
    """Return how many times the customer has complained on this shipment."""
    return {"wbn": wbn, "count": _c("complaint_count")}


# --- action tools (do something) ---
def send_notification(wbn: str = "", channel: str = "email") -> dict[str, Any]:
    return _log(f"📧 Notified customer about delay for {wbn or 'order'} via {channel}")


def reschedule_delivery(wbn: str = "", date: str = "tomorrow") -> dict[str, Any]:
    return _log(f"📅 Rescheduled delivery for {wbn or 'order'} to {date}")


def escalate_to_manager(wbn: str = "") -> dict[str, Any]:
    return _log(f"⏫ Escalated {wbn or 'order'} to a manager")


# --- refund-flow tools ---
def get_order_status(wbn: str = "") -> dict[str, Any]:
    """Return mock order status used for refund decisions."""
    return {"wbn": wbn, "delivered": _c("delivered"),
            "days_since_delivery": _c("days_since_delivery"), "amount": _c("amount")}


def approve_refund(wbn: str = "") -> dict[str, Any]:
    return _log(f"✅ Approved refund for {wbn or 'order'}")


def reject_refund(wbn: str = "") -> dict[str, Any]:
    return _log(f"🚫 Rejected refund for {wbn or 'order'}")


# --- content-moderation tools (a different domain) ---
def get_report(content_id: str = "") -> dict[str, Any]:
    """Return mock report data for a piece of reported content."""
    return {"content_id": content_id, "toxicity_score": _c("toxicity_score"),
            "prior_violations": _c("prior_violations")}


def remove_content(content_id: str = "") -> dict[str, Any]:
    return _log(f"🗑️ Removed content {content_id or ''}")


def send_to_moderator(content_id: str = "") -> dict[str, Any]:
    return _log(f"👤 Sent content {content_id or ''} to a human moderator")


def dismiss_report(content_id: str = "") -> dict[str, Any]:
    return _log(f"✔️ Dismissed report for content {content_id or ''}")


def suspend_account(content_id: str = "") -> dict[str, Any]:
    return _log(f"⛔ Suspended the account for content {content_id or ''}")


# --- IT incident tools (a different domain) ---
def get_alert(alert_id: str = "") -> dict[str, Any]:
    """Return mock alert info (severity)."""
    return {"alert_id": alert_id, "severity": _c("severity")}


def page_oncall(alert_id: str = "") -> dict[str, Any]:
    return _log(f"📟 Paged the on-call engineer for alert {alert_id or ''}")


def log_ticket(alert_id: str = "") -> dict[str, Any]:
    return _log(f"🎫 Logged a ticket for alert {alert_id or ''}")


# --- SaaS billing tools (a different domain) ---
def get_subscription(subscription_id: str = "") -> dict[str, Any]:
    """Return mock subscription info (trial flag, failure count)."""
    return {"subscription_id": subscription_id, "on_trial": _c("on_trial"),
            "failure_count": _c("failure_count")}


def cancel_trial(subscription_id: str = "") -> dict[str, Any]:
    return _log(f"🧹 Cancelled trial for subscription {subscription_id or ''}")


def pause_subscription(subscription_id: str = "") -> dict[str, Any]:
    return _log(f"⏸️ Paused subscription {subscription_id or ''}")


def email_customer(subscription_id: str = "") -> dict[str, Any]:
    return _log(f"✉️ Emailed a payment link for subscription {subscription_id or ''}")


TOOL_REGISTRY: dict[str, Tool] = {
    "get_tracking": Tool(
        name="get_tracking",
        description="Fetch shipment tracking info (days_late, status, city) for a waybill.",
        fn=get_tracking,
        params={"wbn": "the waybill / order id"},
        case_fields=["days_late"],
    ),
    "get_facility_status": Tool(
        name="get_facility_status",
        description="Fetch whether the delivery facility is currently overloaded.",
        fn=get_facility_status,
        params={},
        case_fields=["overloaded"],
    ),
    "get_complaint_count": Tool(
        name="get_complaint_count",
        description="Fetch how many times the customer has complained on this shipment.",
        fn=get_complaint_count,
        params={"wbn": "the waybill / order id"},
        case_fields=["complaint_count"],
    ),
    "send_notification": Tool(
        name="send_notification",
        description="Notify the customer (e.g. about a delay). Channel can be email or sms.",
        fn=send_notification,
        params={"wbn": "the waybill / order id", "channel": "email or sms"},
    ),
    "reschedule_delivery": Tool(
        name="reschedule_delivery",
        description="Reschedule the delivery of a shipment to a new date.",
        fn=reschedule_delivery,
        params={"wbn": "the waybill / order id", "date": "new delivery date"},
    ),
    "escalate_to_manager": Tool(
        name="escalate_to_manager",
        description="Escalate the case to a human manager.",
        fn=escalate_to_manager,
        params={"wbn": "the waybill / order id"},
    ),
    "get_order_status": Tool(
        name="get_order_status",
        description="Fetch order status for refunds (delivered, days_since_delivery, amount).",
        fn=get_order_status,
        params={"wbn": "the waybill / order id"},
        case_fields=["delivered", "days_since_delivery", "amount"],
    ),
    "approve_refund": Tool(
        name="approve_refund",
        description="Approve a customer's refund request.",
        fn=approve_refund,
        params={"wbn": "the waybill / order id"},
    ),
    "reject_refund": Tool(
        name="reject_refund",
        description="Reject a customer's refund request.",
        fn=reject_refund,
        params={"wbn": "the waybill / order id"},
    ),
    "get_report": Tool(
        name="get_report",
        description="Fetch a content report's AI toxicity score and the user's prior violations.",
        fn=get_report,
        params={"content_id": "the reported content id"},
        case_fields=["toxicity_score", "prior_violations"],
    ),
    "remove_content": Tool(
        name="remove_content",
        description="Remove a piece of content immediately.",
        fn=remove_content,
        params={"content_id": "the reported content id"},
    ),
    "send_to_moderator": Tool(
        name="send_to_moderator",
        description="Send content to a human moderator for review.",
        fn=send_to_moderator,
        params={"content_id": "the reported content id"},
    ),
    "dismiss_report": Tool(
        name="dismiss_report",
        description="Dismiss a content report (no action needed).",
        fn=dismiss_report,
        params={"content_id": "the reported content id"},
    ),
    "suspend_account": Tool(
        name="suspend_account",
        description="Suspend the user's account.",
        fn=suspend_account,
        params={"content_id": "the reported content id"},
    ),
    "get_alert": Tool(
        name="get_alert",
        description="Fetch an IT alert's severity (e.g. 'critical', 'low').",
        fn=get_alert,
        params={"alert_id": "the alert id"},
        case_fields=["severity"],
    ),
    "page_oncall": Tool(
        name="page_oncall",
        description="Page the on-call engineer.",
        fn=page_oncall,
        params={"alert_id": "the alert id"},
    ),
    "log_ticket": Tool(
        name="log_ticket",
        description="Log a low-priority ticket for an alert.",
        fn=log_ticket,
        params={"alert_id": "the alert id"},
    ),
    "get_subscription": Tool(
        name="get_subscription",
        description="Fetch a subscription's trial flag and payment failure count.",
        fn=get_subscription,
        params={"subscription_id": "the subscription id"},
        case_fields=["on_trial", "failure_count"],
    ),
    "cancel_trial": Tool(
        name="cancel_trial",
        description="Cancel a trial subscription.",
        fn=cancel_trial,
        params={"subscription_id": "the subscription id"},
    ),
    "pause_subscription": Tool(
        name="pause_subscription",
        description="Pause a subscription after repeated payment failures.",
        fn=pause_subscription,
        params={"subscription_id": "the subscription id"},
    ),
    "email_customer": Tool(
        name="email_customer",
        description="Email the customer a payment-update link.",
        fn=email_customer,
        params={"subscription_id": "the subscription id"},
    ),
}


def tool_catalog_text() -> str:
    """Human-readable list of tools for the compiler prompt."""
    lines = []
    for t in TOOL_REGISTRY.values():
        params = ", ".join(f"{k} ({v})" for k, v in t.params.items()) or "no inputs"
        lines.append(f"- {t.name}: {t.description} Inputs: {params}")
    return "\n".join(lines)


def tool_names() -> set[str]:
    return set(TOOL_REGISTRY.keys())
