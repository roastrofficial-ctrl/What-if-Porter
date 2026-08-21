# PORTER Host Runtime Research Synthesis

Status: research arc closed, 2026-08-21.

This document ties together the Host Runtime pressure sequence from canonical
candidate discovery through large-history recovery. The sequence is closed not
because no further optimization is imaginable, but because the current model
has clear semantics, measured operating envelopes, and an explicit boundary
beyond which optimization would require weaker evidence or a new storage model.

## Frozen architectural result

PORTER owns correspondence, acceptance, and custody transitions. A Host Runtime
is locally chosen attention machinery. An adapter is a warm, language-neutral
application boundary. An application owns meaning.

Arrival remains silent:

```text
Package arrival → Porter candidate projection

later independent Host attention → inspection → CL → adapter opportunity
```

Arrival cannot wake a Host, create adapter capacity, schedule work, or claim
application processing.

## What the pressure sequence earned

### Canonical candidate projection

Candidate discovery uses a disposable bounded projection rather than repeated
directory-history interpretation. Missing, stale, malformed, and interrupted
projection states are reconstructable from canonical acceptance and Collection
facts.

### Direct Collection association

Package-to-CL association is reserved before the unchanged atomic CL threshold.
The association cannot create custody because readers require the named
canonical fact. This removed triangular historical CL scans and improved the
10,000-item serial drain from 847.4 seconds to 21.1 seconds.

### Bounded opportunities

Independent adapter waits may overlap through separate warm adapter processes.
The bound includes publication, outstanding offers, and adapter acquisition.
No durable RUNNING, worker, lease, processing, or completion state exists.

Serial remains the default. Fixed capacity is explicit policy for continuously
slow compatible applications.

### Stable elastic capacity

Mixed or bursty Hosts may opt into elastic capacity. Growth requires bounded
process-local evidence of adapter control latency; one slow outlier earns only
one escape lane. Cheap evidence and local idleness shed capacity. Restart
forgets evidence and returns to the initial process.

Arrival neither supplies evidence nor triggers growth.

### Decoupled attention inspection

Completion reaping no longer re-enumerates candidates while capacity is full.
A bounded in-memory candidate snapshot is revalidated against direct canonical
and projection evidence before offer. New arrival waits for a later locally
chosen inspection interval.

At 1,000 blocked candidates, 100 attention turns fell from 2,958 ms and 101
inspections to 0.608 ms and one inspection.

### Ordered truth, concurrent waiting

Concurrent Runtimes publish at most one CL at a time and immediately hand each
completed Collection to an independent adapter lane. Parallel publication is an
experimental control, not the normal model.

This reduced CL tail latency and CPU while retaining slow-application overlap.
The resulting principle is:

> Truth transitions prefer deliberate ordering. Application waiting may proceed
> independently.

### Non-blocking capacity acquisition

Elastic adapter startup is Package-free asynchronous operational work. A start
reserves the same finite opportunity capacity, can be cancelled during the
readiness handshake, and disappears on failure or restart. The isolated
attention-loop cost fell from 49.696 ms to 0.099 ms without claiming a
throughput improvement.

### Audited recovery frontier

Clean startup audits historical canonical and required projection leaves but
parses zero CL JSON. Exact extensions parse only new CLs. Any missing, changed,
or corrupt evidence forces full reconstruction.

At 10,000 facts, warm startup is 3.221 seconds versus 128.485 seconds without a
frontier. The audit remains O(N) because observation cannot safely be compacted
under the present filesystem model.

## Normal operating choices

The conservative deployment remains:

```text
one locally active Runtime
one warm adapter process
ordered individual CL publication
bounded candidate inspection
audited canonical recovery
```

For a known process-safe application with meaningful adapter waits:

```text
--max-inflight-offers N
```

selects a fixed pool. For intermittent or mixed latency:

```text
--max-inflight-offers N --elastic-capacity
```

adds stable evidence, shedding, decoupled inspection, ordered publication, and
non-blocking capacity acquisition. These are local deployment policies, never
Package or protocol semantics.

## Deliberately retained limits

- Crash after CL but before returned control remains ambiguous and may re-offer.
- Multiple Runtime processes can duplicate adapter offers and are not a scaling
  mechanism.
- Kind remains opaque; no fairness, priority, or workload taxonomy was earned.
- Concurrent adapter processes require explicit application compatibility.
- Warm recovery remains O(N) auditing.
- The local canonical filesystem is not defended against a fully compromised
  Host capable of forging content and metadata consistently.
- Operational telemetry and returned-control markers remain disposable and may
  be lost without changing PORTER truth.

These are stated boundaries, not unfinished scheduler features.

## Stop condition

The final compaction experiment demonstrated a 15,000x faster directory-root
shortcut which silently missed leaf corruption. It was rejected. That negative
result supplies the stop condition for this research arc.

Further Host Runtime optimization should require one of:

- measured production pressure outside the tested envelope;
- a new storage-integrity primitive with an explicit authority model;
- application evidence that current serial/fixed/elastic choices are
  insufficient; or
- a semantic problem, not merely an attractive scheduler mechanism.

Until then, the architecture is coherent enough to use rather than continually
optimize.
