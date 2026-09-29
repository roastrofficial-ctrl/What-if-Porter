"""PORTER-CANONICAL-JSON/1: strict JSON input and RFC 8785 output."""
from __future__ import annotations

import json
import math

import rfc8785


def _number(value):
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError('number outside binary64 domain') from exc
    if not math.isfinite(result):
        raise ValueError('non-finite JSON number')
    if abs(result) <= 9007199254740991 and result.is_integer():
        return int(result)
    return result


def _normalize(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        value.encode('utf-8', errors='strict')
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('JSON object names must be strings')
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    raise ValueError('unsupported JSON value')


def canonical(value) -> bytes:
    return rfc8785.dumps(_normalize(value))


def _object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate JSON object name')
        result[name] = value
    return result


def _constant(value):
    raise ValueError('non-JSON numeric constant: ' + value)


def loads(encoded: bytes | str):
    if isinstance(encoded, bytes):
        encoded = encoded.decode('utf-8', errors='strict')
    if encoded.startswith('\ufeff'):
        raise ValueError('JSON BOM is forbidden')
    value = json.loads(encoded, object_pairs_hook=_object, parse_int=_number,
                       parse_float=_number, parse_constant=_constant)
    # Validate Unicode, including keys, before exposing the parsed tree.
    canonical(value)
    return value
