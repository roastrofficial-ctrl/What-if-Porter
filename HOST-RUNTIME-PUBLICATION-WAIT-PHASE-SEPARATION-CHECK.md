# PORTER Canonical Publication and Adapter-Wait Phase Separation Check

Status: experiment complete, 2026-08-21.

This experiment asks whether concurrency belongs after custody transfer rather
than across it. The candidate model deliberately orders canonical Collection
publication while allowing already-collected adapter offers to wait and return
control independently.

The result supports the principle:

> Truth transitions prefer deliberate ordering. Application waiting may proceed
> independently.

All frozen Package, AC, CL, Return, Kind, Host Runtime, adapter, duplicate, and
application-meaning semantics remain unchanged.

## Models compared

The serial control has one publication path and one adapter lane:

```text
CL-A → offer A → wait → CL-B → offer B → wait
```

The preceding concurrent control runs the whole opportunity lifecycle in each
thread:

```text
thread A: CL-A → offer A → wait
thread B: CL-B → offer B → wait
thread C: CL-C → offer C → wait
thread D: CL-D → offer D → wait
```

The separated model uses the Runtime's chosen visit as the single publisher and
hands each completed Collection immediately to an independent adapter lane:

```text
CL-A → lane A waits
CL-B → lane B waits
CL-C → lane C waits
CL-D → lane D waits
```

Publication is neither a batch nor one transaction. Every Package crosses its
unchanged individual atomic CL threshold before the next publication begins.
Adapter A may return while B, C, or D is being published or waiting.

## Bound and absence of a queue

The existing opportunity bound covers the one publication currently in progress
plus all adapter offers awaiting control. With a bound of four, three lanes plus
one publication is four; after immediate handoff, four lanes is four. The
Runtime cannot publish a fifth CL until capacity returns.

There is no durable or process-level collected-work queue. Publication and
executor handoff occur in the same local call path. A process interruption can
still land after CL and before adapter offer, but that gap already exists in the
frozen Runtime contract and is resolved by re-offer after canonical recovery.
It is not named RUNNING, queued, claimed, processing, leased, failed, or
complete.

One adapter instance still receives at most one offer at a time. Parallelism is
therefore exactly the number of independent application waits, never concurrent
calls through one adapter stream.

## Crash-gap correction

The explicit CL-before-offer crash vector exposed a recovery regression caused
by the preceding direct-association optimization. Startup recovery correctly
found the canonical CL, but candidate selection treated its now-present direct
association like a stale Porter candidate and suppressed the re-offer.

Selection now distinguishes:

- a projected candidate with an association: stale projection, settle it;
- a CL discovered during recovery without returned-control evidence: re-offer
  the existing Collection.

The conformance vector interrupts after exactly one CL, observes no adapter
offer, no returned marker, and no queue/running state, then restarts. The second
Runtime offers the same one canonical CL exactly once. This restores the frozen
crash meaning rather than adding retry semantics.

## Pressure results

All measurements use direct Collection association. `parallel publication`
allows four concurrent CL/projection paths. `separated` permits one publication
and four independent adapter waits.

| Candidates | Adapter wait | Serial | Parallel publication | Separated |
|---:|---:|---:|---:|---:|
| 200 | 0 ms | 7.201 s | 3.001 s | 2.537 s |
| 500 | 0 ms | 23.232 s | 8.350 s | 8.157 s |
| 200 | 10 ms | 20.293 s | 3.413 s | 2.919 s |
| 100 | 100 ms | 20.580 s | 4.811 s | 4.596 s |

The separated model beat parallel publication in every cell: 15.4% at 200
zero-delay candidates, 2.3% at 500, 14.5% with 10 ms waits, and 4.5% with 100 ms
waits. More importantly, it retained the roughly four-lane application-wait
gain over serial execution.

Filesystem behavior explains the result:

| Shape | Parallel CL median / p99 | Separated CL median / p99 | CPU change |
|---|---:|---:|---:|
| 200 × 0 ms | 6.904 / 33.655 ms | 5.273 / 8.159 ms | −35.7% |
| 500 × 0 ms | 7.124 / 20.336 ms | 5.573 / 9.927 ms | −24.3% |
| 200 × 10 ms | 6.319 / 66.462 ms | 5.272 / 10.135 ms | −33.2% |
| 100 × 100 ms | 11.903 / 48.312 ms | 11.498 / 27.538 ms | +3.8% |

Publication concurrency widened tail latency dramatically. Ordering reduced CL
p99 by 51–85% in these runs. The small CPU increase in the 100 ms cell is noise
within a latency-dominated, short trial; drain and publication tail still
improved. At 500 zero-delay candidates, median CL-to-offer latency fell from
12.527 to 7.143 ms.

Raw measurements are in `benchmarks/results/phase-separation.json`.

## Failure and operational behavior

If canonical publication fails before CL, the unused adapter lane returns to
the local pool and no custody transition exists. If the process disappears
after CL but before handoff, restart re-offers from canonical recovery. If an
adapter hangs after handoff, it occupies one lane while other lanes return
independently. If an adapter fails, the existing policy retires that instance
without inventing a Runtime retry claim.

Shutdown stops selection of new opportunities, never batches pending
publications, and applies the existing grace to adapter lanes. Process-local
publication counters and handoff futures vanish on crash.

Parallel publication remains available only as the explicit experimental
`--parallel-publication` control. Concurrent Runtimes default to ordered
publication; `--serial-publication` states that policy explicitly. The ordinary
one-adapter serial Runtime is unchanged.

## Conformance

New vectors prove publication concurrency never exceeds one, four adapter waits
can overlap, publication plus waits never exceeds the opportunity bound, the
CL-before-offer crash gap creates no queue state and recovers correctly, and the
existing hung, mixed-latency, arrival-causality, stale-snapshot, and no-running-
state vectors continue to hold.

The complete dependency-equipped Docker suite passes: **134 tests**. Focused
opportunity and custody tests, compilation, and whitespace checks also pass.

## Verdict

Phase separation earns itself and becomes the normal concurrent Runtime model.
The performance case is consistent, but the architectural result is stronger:
the reason to overlap opportunities was independent application waiting. There
was no corresponding evidence that custody transitions benefited from being
made concurrent.

PORTER therefore does not indiscriminately parallelise the request lifecycle.
It orders canonical truth transitions, hands each completed transition directly
to a bounded independent lane, and overlaps only the application-controlled
wait.

The one next experiment is **Non-Blocking Adapter Capacity Acquisition**:
determine whether elastic process startup can occur as a bounded in-memory
capacity reservation without pausing completion reaping or ordered publication,
while a starting adapter counts against the same opportunity maximum and gains
no durable scheduler identity.
