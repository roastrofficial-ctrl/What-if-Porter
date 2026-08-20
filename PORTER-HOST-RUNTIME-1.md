# PORTER-HOST-RUNTIME/1

Status: **FROZEN**

## Purpose

`PORTER-HOST-RUNTIME/1` is the smallest generic local machine that lets an
isolated Host choose attention, take custody of PORTER correspondence, and make
that Host-owned correspondence available to application machinery.

It provides opportunity, not application execution semantics:

```text
Host-local policy chooses attention
  → inspect local candidate metadata
  → validate against canonical AC and CL
  → choose a finite set
  → establish CL independently for each Package
  → offer the canonical Collection to local application machinery
```

Everything after the offer may have application meaning. The Runtime does not.

## Normative requirements

An implementation conforming to this contract:

1. MUST operate on the Host side of a local Host–Porter boundary.
2. MUST NOT require an external network interface or listener.
3. MUST inspect only when Host-local lifecycle policy chooses an attention
   opportunity. Arrival, AC publication, candidate mutation and native carriage
   MUST NOT start, wake, signal or schedule it.
4. MAY use configured opaque Kind values to narrow candidate inspection. It MUST
   NOT interpret payloads or map Kind to application handlers.
5. MUST validate selected candidate identity and Kind against canonical AC and
   current CL before Collection. A candidate projection is never authority.
6. MUST establish or recover exactly one canonical CL before offering a Package
   to application machinery. The offered value MUST identify that CL and contain
   the recoverable Package.
7. MUST treat each Collection independently. A finite multi-item visit is not a
   transaction, establishes no batch fact, and has no rollback.
8. MUST preserve already-published CL after interruption. Packages without CL
   remain recipient Porter responsibility.
9. MUST NOT claim application start, success, failure, completion, commitment,
   acknowledgement, retry, or disposition.
10. MUST NOT require a Return, require outbound correspondence during the same
    opportunity, or assume outbound correspondence is related to the offered
    Package.
11. MUST NOT lodge outbound correspondence on the application's behalf by
    inferring motivation. Application machinery MAY independently use the local
    Porter Lodgement interface.
12. MUST permit local shutdown between independent offers. Shutdown during an
    offer MAY require ordinary crash recovery; it creates no cross-boundary
    transaction.
13. MAY record operational observations. They MUST be removable without changing
    PORTER or application truth and MUST NOT serve as application evidence.

## Knowledge boundary

| Event or value | Porter | Runtime | Adapter | Application |
|---|:---:|:---:|:---:|:---:|
| candidate hint exists | yes | yes | no requirement | no requirement |
| AC exists | yes | validates | via Collection context | may inspect locally |
| CL exists | yes | establishes/recovers | receives identity and fact | may retain |
| Package bytes and Kind | yes | conveys opaquely | yes | yes |
| payload meaning | no | no | may know | yes |
| application started/effect/commit | no | no | may know | yes |
| Return drafted | no | no | may know | yes |
| Return lodged | as independent LG | no inference | may know | yes |
| journey complete | no generic claim | no | application-specific | application-specific |

The Runtime knows that canonical Host custody exists and that a local offer was
made. It never knows what the Host considered useful.

## Collection and interruption

The threshold ordering is fixed:

```text
candidate hint
  → canonical validation
  → canonical CL
  → recoverable Host custody
  → adapter offer
```

An interruption after CL and before adapter entry leaves `FACT EXISTS`: the
Host owns recoverable correspondence and a later chosen opportunity can offer
the same Collection. An interruption after adapter entry is application-
ambiguous. PORTER and Runtime do not decide whether an application effect should
be repeated.

An implementation may retain an operational returned-control observation to
avoid needless re-offer. Before that observation, a later lifecycle may re-offer
the same immutable Collection. Loss of operational state may also cause re-offer.
Adapters therefore must tolerate duplicate opportunity; this is not an
application retry guarantee.

## Policy ownership

| Concern | Owner |
|---|---|
| arrival, AC, CL and candidate validation | Porter / Runtime boundary |
| which Kinds merit attention | Host-local configuration or policy |
| when to inspect and how long to idle | deployment/operator Host lifecycle |
| maximum items in one visit | deployment/operator policy |
| ordering | unspecified; implementation determinism only |
| adapter process lifetime | implementation/deployment |
| application timeout and retry | application/deployment |
| shutdown request | Host lifecycle/deployment |
| Return and unrelated Lodgement | application using Porter locally |

Batch size, sleep duration, process model, thread model and candidate order are
not protocol semantics. A conforming implementation may be episodic, continuous,
or one-shot, and may choose visits of one or many independent opportunities.

## Local IPC abstraction

The contract requires semantic operations equivalent to:

- inspect candidate identities and opaque Kinds locally;
- validate them against canonical custody;
- collect one Package and obtain its canonical Collection fact;
- offer that fact to local application machinery;
- optionally observe local control return;
- lodge application-chosen outbound Packages through the existing local Porter
  interface.

It does not require Python, SQLite, filesystem paths, JSON Lines, Docker,
`os.scandir`, processes or threads. A Rust implementation may use different
local mechanics while preserving these observations and prohibitions.

## Non-goals

The Runtime is not an application server, request router, job queue, disposition
store, retry scheduler, response broker, transaction manager, network Porter, or
security sandbox. A same-privilege malicious adapter may attack shared local
resources; deployment isolation is outside this contract.

## Reference implementation

The Python `porter.host_runtime` is one executable reference implementation.
Its configured Kind set, bounded visits, retained adapter process, polling sleep,
filesystem IPC and operational journal are implementation choices, not the
definition above.
