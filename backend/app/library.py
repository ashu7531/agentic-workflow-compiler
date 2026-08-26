"""A tiny SOP library — represents a company's collection of procedures.

Two things:
  1. SAMPLE_SOPS  — ready-made example procedures the user can load.
  2. saved store  — compiled workflows the user saves (persisted best-effort to
                    a local JSON file so they survive a restart in local dev).

On serverless hosts the filesystem is ephemeral, so persistence is best-effort;
the in-memory list always works for the current session.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_STORE_PATH = os.path.join(_DATA_DIR, "library.json")


# Examples across domains, with a mix of SHORT and LONG conditions.
# Each maps to a canned graph in mock mode; with a Gemini key, any text compiles.
SAMPLE_SOPS: list[dict[str, str]] = [
    {
        "id": "sample_incident",
        "title": "IT incident (short) — Ops",
        "sop_text": (
            "When a service alert fires: if the severity is critical, page the on-call "
            "engineer; otherwise just log a ticket."
        ),
    },
    {
        "id": "sample_refund",
        "title": "Refund request (medium) — E-commerce",
        "sop_text": (
            "When a customer requests a refund: if the amount is over 5000, escalate to a "
            "manager. Otherwise, if the order was delivered and it is within 7 days, approve "
            "the refund; if not, reject it."
        ),
    },
    {
        "id": "sample_saas",
        "title": "Payment failure (medium) — SaaS billing",
        "sop_text": (
            "When a payment fails: if the customer is on a trial, cancel the trial. Otherwise, "
            "if the payment has failed 3 or more times, pause the subscription; if not, email "
            "the customer a payment-update link."
        ),
    },
    {
        "id": "sample_delay",
        "title": "Delivery delay (long) — Logistics",
        "sop_text": (
            "When an order is delayed more than 3 days and the warehouse is overloaded, "
            "notify the customer; otherwise reschedule the delivery. "
            "If the customer has complained twice, escalate to a manager."
        ),
    },
    {
        "id": "sample_moderation",
        "title": "Content moderation (long) — Trust & Safety",
        "sop_text": (
            "When content is reported: if the AI toxicity score is above 0.9, remove it "
            "immediately. If it's between 0.6 and 0.9, send it to a human moderator. Below "
            "that, dismiss the report. If the user has 3 prior violations, suspend the account."
        ),
    },
]


# ── in-memory saved store (loaded from disk if present) ──
_saved: list[dict[str, Any]] = []


def _load() -> None:
    global _saved
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            _saved = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _saved = []


def _persist() -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(_saved, f, indent=2)
    except OSError:
        pass  # best-effort (e.g. read-only serverless FS)


_load()


def list_saved() -> list[dict[str, Any]]:
    # return without the (large) graph payload for the list view
    return [{"id": s["id"], "title": s["title"], "sop_text": s["sop_text"]} for s in _saved]


def get_saved(item_id: str) -> dict[str, Any] | None:
    return next((s for s in _saved if s["id"] == item_id), None)


def save(title: str, sop_text: str, graph: dict[str, Any]) -> dict[str, Any]:
    item = {"id": uuid.uuid4().hex[:8], "title": title or "Untitled workflow",
            "sop_text": sop_text, "graph": graph}
    _saved.append(item)
    _persist()
    return {"id": item["id"], "title": item["title"]}


def delete(item_id: str) -> bool:
    global _saved
    before = len(_saved)
    _saved = [s for s in _saved if s["id"] != item_id]
    if len(_saved) != before:
        _persist()
        return True
    return False
