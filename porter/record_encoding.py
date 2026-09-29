"""Existing authority-signature binding; not a Package digest fallback."""
import json


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
