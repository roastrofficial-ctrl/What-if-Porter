# PORTER-HOST-ADAPTER/1

Status: **FROZEN**

## Abstract contract

The adapter boundary means only:

> Here is correspondence already recoverable in Host custody. Exercise whatever
> application-owned behaviour is locally appropriate, then optionally return
> control to the Runtime.

An offer contains:

- a Runtime-local opaque dispatch identity;
- one complete canonical `COLLECTION` fact;
- the Package contained by that fact.

The adapter MUST NOT be asked to acknowledge AC or create CL. Both precede the
offer. Returning control says only that the adapter call/interaction returned.
It MUST NOT mean processed, succeeded, failed, completed, committed, retried,
acknowledged, or that a Return exists.

The adapter:

- MAY interpret Kind and payload;
- MAY persist application-owned facts, effects, intentions and recovery state;
- MAY produce no outbound correspondence;
- MAY lodge a related Return now or during a later Host execution;
- MAY lodge unrelated or multiple Packages through the ordinary local Porter
  interface;
- MAY decline, crash, exit or remain busy;
- MUST tolerate receiving the same Collection opportunity again after ambiguous
  Runtime/adapter control loss;
- MUST own the meaning of any repeated application action.

Application cadence, retry, timeout, continuation and durability are not fields
in this contract.

## Reference JSON Lines binding

The Python reference uses a warm local child process. UTF-8 JSON objects are
separated by LF. This binding is language-neutral but not required of other
Runtime implementations.

Readiness:

```json
{"contract":"PORTER-HOST-ADAPTER/1","runtime_observation":"ADAPTER_READY"}
```

Offer:

```json
{
  "contract": "PORTER-HOST-ADAPTER/1",
  "dispatch": "opaque-runtime-identity",
  "collection": {"protocol":"PORTER/1","kind":"COLLECTION"}
}
```

Optional control return:

```json
{
  "contract": "PORTER-HOST-ADAPTER/1",
  "dispatch": "opaque-runtime-identity",
  "runtime_observation": "ADAPTER_RETURNED_CONTROL"
}
```

The contract and dispatch identity must match. The reference Runtime ignores
unknown extra fields and places no semantic meaning on them. In particular,
`next_visit_ms` is no longer interpreted; cadence belongs to Host deployment
policy. Reference adapter control lines are bounded to 65,536 characters.

Malformed, oversized, missing or mismatched control output causes an operational
Runtime error after CL. It creates no generic application fact. An adapter that
hangs blocks the current serial reference interaction until it returns or an
operator terminates the lifecycle; there is deliberately no generic application
timeout.

## Outbound interface

Outbound correspondence does not travel in the control return. The application
uses the Host's existing local Porter Lodgement interface and supplies the full
PORTER Package, identity, Kind and optional `in_reply_to`. PORTER owns Lodgement
validation and facts. Runtime does not infer whether the motivation was a Return,
continuation, fan-out, unrelated notice, or something else.

## Language independence

The boundary exposes only named records, strings, integers, booleans, arrays,
objects and null. It exposes no Python exceptions, generators, `Path` objects,
async tasks, Laravel requests, container bindings or queue jobs. PHP Find Me,
Python HarmonicDB and the tiny transformation Host conform unchanged.
