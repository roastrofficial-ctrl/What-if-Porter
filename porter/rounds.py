from __future__ import annotations

import uuid
from pathlib import Path

from .lodgement import atomic_json, now_ms
from .tickets import inspect


def _event_at(ticket: dict, kind: str) -> int | None:
    times = [int(item["at_ms"]) for item in ticket.get("events", []) if item.get("event") == kind]
    return max(times) if times else None


def _observation(ticket: dict, observed_at: int) -> dict:
    value = {
        "ticket": ticket["ticket"],
        "package": ticket["package"],
        "state": ticket["state"],
        "held_returns": ticket["held_returns"],
        "duplicate_returns": ticket["duplicate_returns"],
        "carriage_knowledge": ticket["carriage_knowledge"],
        "carriage_attempts": ticket["carriage_attempts"],
    }
    if "acceptance_evidence" in ticket: value["acceptance_evidence"] = ticket["acceptance_evidence"]
    held_at = _event_at(ticket, "RETURN_HELD")
    if held_at is not None:
        value["return_held_at_ms"] = held_at
        value["observation_latency_ms"] = max(0, observed_at - held_at)
        lodged_at = _event_at(ticket, "LODGED")
        if lodged_at is not None:
            value["lodged_at_ms"] = lodged_at
            value["carriage_latency_ms"] = max(0, held_at - lodged_at)
    return value


def make_round(ipc, ticket_ids: list[str], initiated_by: str = "HOST") -> dict:
    """Inspect several Tickets and publish one durable, client-local Round fact.

    A Round observes only. It never collects, schedules, or continues Host work.
    """
    if not ticket_ids:
        raise ValueError("a PORTER Round requires at least one Collection Ticket")
    began_at = now_ms()
    # The Round journal is the durable record of this observation. Rewriting
    # every mutable Ticket with the same TICKET_INSPECTED narration duplicates
    # that fact N times and makes observation scale with unrelated history.
    snapshots = [inspect(ipc, ticket_id, record=False) for ticket_id in ticket_ids]
    observed_at = now_ms()
    round_id = f"RD-{uuid.uuid4().hex}"
    value = {
        "vocabulary": "PORTER-ROUNDS/1",
        "round": round_id,
        "initiated_by": initiated_by,
        "began_at_ms": began_at,
        "observed_at_ms": observed_at,
        "observations": [_observation(snapshot, observed_at) for snapshot in snapshots],
    }
    atomic_json(Path(ipc) / "rounds" / f"{round_id}.json", value)
    return value
