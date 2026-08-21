# PORTER Host Runtime Attention Loop Inspection Decoupling Check

Status: experiment complete, 2026-08-21.

This experiment separates cheap completion reaping from expensive candidate
re-enumeration. It asks whether an already-attentive Host can retain a bounded,
process-local view of previously inspected pressure without turning that view
into custody truth, a work queue, or an arrival-triggered scheduler.

The frozen Runtime, adapter, Package, AC, CL, Return, Kind, duplicate, and
application-meaning semantics remain unchanged.

## The amplification

Elastic capacity needs to observe both returned control and remaining pressure.
The first implementation called full `candidates()` enumeration on every
chosen visit, even while all adapters were occupied. A one-millisecond reap
cadence could therefore perform hundreds of acceptance reads and candidate
index traversals despite being unable to offer another Package.

This was neither canonical work nor useful attention. It also polluted elastic
timing: the loop spent more effort rediscovering unchanged pressure than
observing adapter control.

## Decoupled loop

The Runtime now keeps at most one normal selection batch as a process-local
candidate snapshot. The snapshot is populated only by a Host-chosen inspection
and is consumed in the same deterministic order returned by the existing
candidate projection.

Each visit performs work in this order:

```text
reap completed adapter control
  → evaluate existing latency evidence and cached pressure
  → if capacity exists, consume already-inspected candidates
  → only if the snapshot is empty and the local interval permits, inspect again
```

When capacity is full, reaping and pressure evaluation do not enumerate the
candidate directory. When a batch is exhausted, a later locally chosen visit
may inspect the next batch. When no work was previously visible, new arrival is
not noticed until the configured local inspection interval expires and another
visit occurs.

The default operational interval is 50 ms and can be selected with:

```text
--elastic-inspection-interval-ms 50
```

It is neither a delivery deadline nor a protocol value.

## Snapshot authority

The snapshot has no authority. Immediately before submitting a cached identity,
the Runtime directly revalidates:

- it is not already submitted locally;
- no returned-control marker suppresses it;
- canonical acceptance still exists;
- the canonical Package still matches the opaque Kind filter; and
- no Package-to-CL association now exists.

A stale identity is discarded without an offer. Normal later candidate
inspection reconciles its disposable projection. Consequently caching can
delay or reorder attention within the contract's already-unspecified ordering,
but cannot create acceptance, Collection, eligibility, or application meaning.

The snapshot, inspection timestamp, count, and timing vanish on crash. Restart
recovers canonical Collections as before and begins with an empty snapshot.

## Causal arrival boundary

An explicit test performs an empty inspection, deposits a Package, and invokes
several visits before the inspection interval. There is no new inspection, CL,
or adapter offer. After the interval, a later chosen visit inspects and may act.

Thus the causal chain remains:

```text
arrival → silent candidate projection

later independent Host visit → locally permitted inspection → possible offer
```

Arrival neither invokes the Runtime nor invalidates, refreshes, or wakes its
snapshot.

## Pressure results

The eager control and snapshot policy used the same candidate implementation
and filesystem.

### Full capacity

With 1,000 candidates, one blocked adapter, and 100 additional attention-loop
turns:

| Policy | Inspections | Inspection time | 100-turn probe |
|---|---:|---:|---:|
| Eager | 101 | 3,062.045 ms | 2,958.257 ms |
| Snapshot | 1 | 86.937 ms | 0.608 ms |

The full-capacity loop became roughly 4,866x faster because it performed the
appropriate amount of filesystem inspection: none. Completion reaping and
signal responsiveness remain available on every turn.

### Slow drain

With 200 candidates, 10 ms adapter calls, and elastic capacity up to four:

| Policy | Drain | Inspections | Inspection time | Returns | Peak |
|---|---:|---:|---:|---:|---:|
| Eager | 2,764.527 ms | 123 | 2,558.545 ms | 200 | 4 |
| Snapshot | 2,023.234 ms | 5 | 155.525 ms | 200 | 4 |

The snapshot removed 95.9% of enumerations, reduced measured inspection time by
93.9%, and shortened the drain by 26.8%. Both policies returned control for all
200 offers and reached the same bounded opportunity capacity.

Raw measurements are in
`benchmarks/results/inspection-decoupling.json`.

## Failure and competition

If another Runtime collects a cached Package, direct pre-offer validation drops
the stale identity. If competition occurs after validation, the existing
per-Package Collection lock and canonical CL rule remain the authority; the
unchanged duplicate-offer possibility still applies. Snapshotting neither fixes
nor worsens that semantic allowance deliberately.

If a Runtime crashes after inspection, no other process inherits the snapshot.
No Package has moved unless canonical CL publication occurred. If it crashes
after CL, existing recovery applies. A corrupted or lost snapshot is equivalent
to forgetting what the Runtime recently looked at.

## Conformance

New vectors cover full-capacity reap loops, stale cached candidates, delayed
visibility of new arrival, bounded batch inspection, and the existing mixed
latency, hung adapter, restart, crash, and no-durable-running-state shapes.

The complete dependency-equipped Docker suite passes: **131 tests**. Focused
opportunity and custody tests, compilation, and whitespace validation also
pass.

## Verdict

Inspection decoupling earns itself. The snapshot is bounded operational memory,
not a queue; canonical facts are checked before offer; arrival remains silent;
and the dominant repeated filesystem work disappears without reducing useful
capacity.

The one next experiment is **Canonical Publication and Adapter-Wait Phase
Separation**: determine whether CL publication should remain deliberately
ordered while already-collected offers wait concurrently in independent
adapters, preserving the same total opportunity bound and avoiding a durable
collected-work queue. This directly tests the filesystem contention still seen
when several opportunity threads publish canonical and disposable projections
simultaneously.
