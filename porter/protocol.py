from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

PROTOCOL = "PORTER/1"
IDENTITY = re.compile(r"^[a-z][a-z0-9.-]{0,127}$")


def package(
    sender, recipient, kind, payload, *, reply_to=None, in_reply_to=None, ttl=300
):
    now = int(time.time())
    value = {
        "protocol": PROTOCOL,
        "package": "PKG-" + uuid.uuid4().hex,
        "from": sender,
        "to": recipient,
        "kind": kind,
        "created": now,
        "expires": now + ttl,
        "payload": payload,
    }
    if reply_to:
        value["reply_to"] = reply_to
    if in_reply_to:
        value["in_reply_to"] = in_reply_to
    validate(value)
    return value


def validate(value):
    required = {
        "protocol",
        "package",
        "from",
        "to",
        "kind",
        "created",
        "expires",
        "payload",
    }
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value["protocol"] != PROTOCOL
    ):
        raise ValueError("invalid PORTER/1 Package envelope")
    if (
        not IDENTITY.fullmatch(value["from"])
        or not IDENTITY.fullmatch(value["to"])
        or not IDENTITY.fullmatch(value["kind"])
    ):
        raise ValueError("invalid PORTER/1 identity or Kind")
    if not isinstance(value["payload"], dict):
        raise ValueError("Package payload must be an opaque object")
    if value["expires"] <= value["created"]:
        raise ValueError("Package expiry must follow creation")
    return value


def atomic_write(folder, value):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (value["package"] + ".json")
    temporary = folder / ("." + value["package"] + ".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")) + "\n")
    os.replace(temporary, target)
    return target
