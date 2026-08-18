#!/usr/bin/env python3
"""Two deliberately networkless Hosts for the PORTER Public House demo."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from porter.custody import collect_package
from porter.protocol import package
from porter.tickets import collect, inspect, lodge

IPC = Path("/ipc")
TIMEOUT = 30


def assert_host_isolated() -> None:
    if Path("/sys/class/net/eth0").exists():
        raise RuntimeError("a demo Host unexpectedly has a network interface")


def wait_for_package() -> dict:
    while True:
        candidates = sorted((IPC / "inbox").glob("PKG-*.json"))
        if candidates:
            return json.loads(candidates[0].read_text())
        time.sleep(0.05)


def serve() -> None:
    assert_host_isolated()
    while True:
        request = wait_for_package()
        collection = collect_package(IPC, request["package"], "taproom-host")
        if request["kind"] != "demo.pint":
            continue

        response = package(
            "taproom",
            request["reply_to"],
            "porter.return",
            {
                "served": "A pint of Asynchronous Best",
                "note": (
                    "The Taproom Host collected your Package; arrival did not "
                    "call or enter the Host. This Return is a new Package."
                ),
                "request_journey": {
                    "package": request["package"],
                    "accepted_by": "taproom",
                    "acceptance": collection["acceptance"],
                    "host_collection": collection["collection"],
                },
            },
            in_reply_to=request["package"],
        )
        return_ticket = lodge(IPC, response)
        print(
            f"Taproom served {request['package']} as Return {response['package']} "
            f"under Lodgement {return_ticket['lodgement']}",
            flush=True,
        )


def wait_for_return(ticket_id: str) -> dict:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        view = inspect(IPC, ticket_id, record=False)
        if view["state"] == "RETURN_HELD":
            return collect(IPC, ticket_id)
        time.sleep(0.05)
    raise RuntimeError("the Visitor Host found no held Return")


def visit() -> None:
    assert_host_isolated()
    request = package(
        "visitor",
        "taproom",
        "demo.pint",
        {"order": "One illustrative pint, please"},
        reply_to="visitor",
    )
    request_ticket = lodge(IPC, request)
    result = wait_for_return(request_ticket["ticket"])
    response = result["package"]
    receipt = json.loads((IPC / "receipts" / f"{request['package']}.json").read_text())
    journey = {
        "request": {
            "package": request["package"],
            "lodgement": request_ticket["lodgement"],
            "collection_ticket": request_ticket["ticket"],
            "remote_acceptance": receipt["acceptance"],
            "accepted_by": response["payload"]["request_journey"]["accepted_by"],
            "host_collection": response["payload"]["request_journey"][
                "host_collection"
            ],
        },
        "return": {
            "package": response["package"],
            "in_reply_to": response["in_reply_to"],
            "visitor_collection": result["collection"],
        },
    }

    print("\nPORTER PUBLIC HOUSE")
    print(f"Served: {response['payload']['served']}")
    print(response["payload"]["note"])
    print("\nThe durable journey:")
    print(json.dumps(journey, indent=2))
    print("\nNeither Host had a network interface. The Porters carried both Packages.")


if __name__ == "__main__":
    try:
        {"serve": serve, "visit": visit}[sys.argv[1]]()
    except (IndexError, KeyError):
        raise SystemExit("usage: service.py serve|visit")
