# PORTER Host Runtime Elastic Opportunity Capacity Check

Status: experiment complete, 2026-08-20.

This experiment asks whether a Host which is already attentive may temporarily
increase its local adapter capacity when its own observations justify doing so,
then shed that capacity when it ceases to help. It does not ask whether Package
arrival may scale a Host. It may not.

`PORTER-HOST-RUNTIME/1`, `PORTER-HOST-ADAPTER/1`, Package, AC, CL, Return, Kind,
and application meaning remain frozen.

## Decision before implementation

Elasticity had to beat a deliberately sceptical null hypothesis: one warm
process plus an explicit fixed bound might already be sufficient. The elastic
policy would be earned only if it:

1. stayed at one process for cheap work;
2. approached fixed-4 throughput for independently slow work;
3. returned to one warm process after locally observed idleness;
4. created no capacity merely because a Package arrived;
5. introduced no durable scheduler truth or new retry meaning; and
6. remained an explicit, bounded, application-compatible deployment choice.

## Causal boundary

The implemented chain is:

```text
already-running Host Runtime
  → locally chosen visit
  → candidate backlog plus observed slow adapter control
  → locally create at most one additional warm adapter on that visit
```

The forbidden chain remains impossible:

```text
Package arrival → candidate projection → adapter creation
```

Porter deposit and candidate publication have no reference to the elastic
Runtime, its process factory, or its capacity. A conformance test deposits ten
Packages and waits longer than the growth threshold without running a visit;
capacity stays at one and the factory is never called.

## Smallest policy tested

`ElasticOpportunityRuntime` begins with exactly one adapter and has an explicit
maximum (four in this experiment). During a chosen visit it may grow by one when
all of the following are locally true:

- candidates remain beyond immediately available capacity;
- an adapter call currently exceeds the configured slow-control threshold, or
  the most recently completed adapter call exceeded it; and
- the configured maximum has not been reached.

It does not treat CL publication, returned-control marker publication, candidate
inspection, or a delayed reap as application slowness. An early implementation
did so and falsely scaled cheap work. That result was rejected; the measurement
now brackets only the frozen adapter `dispatch()` control interval.

When a chosen visit observes no candidates, no outstanding offers, and a local
idle interval beyond the shedding threshold, it retires one unused adapter. It
eventually returns to the single warm baseline. Growth and shedding events,
adapter assignment, futures, latency samples, and timers are process-local and
disappear on crash.

CLI policy is explicit:

```text
--max-inflight-offers 4 --elastic-capacity
--elastic-slow-offer-ms 5 --elastic-shed-after-ms 1000
```

Without `--elastic-capacity`, the existing meanings remain: maximum one selects
the serial Runtime; a larger maximum selects the fixed pool.

## Pressure result

The compact policy comparison used 100 candidates, direct CL association, a
maximum of four, a 5 ms slow-control threshold, and a modeled 45 ms startup cost
for every elastic growth. The 45 ms value comes from the preceding real Tiny
adapter startup measurement. All three modes in a row ran on the same local
filesystem environment; absolute values should not be compared with the prior
Docker pressure run.

| Adapter delay | Serial | Fixed-4 | Elastic 1→4 | Elastic peak | After idle |
|---:|---:|---:|---:|---:|---:|
| 0 ms | 3.094 s | 1.107 s | 3.085 s | 1 | 1 |
| 10 ms | 5.186 s | 2.032 s | 1.650 s | 4 | 1 |
| 100 ms | 14.788 s | 4.183 s | 3.831 s | 4 | 1 |

The local filesystem happened to favor fixed concurrency even for the zero-cost
adapter in this run, unlike the prior Docker 10,000-item result. That does not
alter the policy finding: elastic stayed within 0.3% of serial and allocated no
extra process because the application itself returned cheaply. At 10 and 100
ms it paid three modeled process starts, reached four, improved over serial by
3.14x and 3.86x respectively, and then shed back to one. Its small apparent win
over fixed-4 is not claimed as a general advantage; it is within environmental
and scheduling variation. Matching the useful fixed bound is the result.

Raw measurements are in `benchmarks/results/elastic-capacity.json`. The larger
1k/10k curves remain owned by the preceding opportunity-scheduling experiment;
this comparison isolates trigger accuracy, startup penalty, and shedding rather
than repeating already-established scale pressure.

## Failure, shutdown, and semantics

The elastic Runtime inherits the bounded opportunity rule: its configured
maximum covers Collection publication in progress plus offers awaiting control.
Growing the process pool never pre-collects beyond that bound.

If process creation fails, it is an operational error and capacity remains
smaller. No Package changes custody because growth failed. If an adapter fails,
that instance is retired without Runtime-invented retry semantics. A hung
adapter consumes one slot while other earned capacity can proceed. Shutdown
stops new offers, applies the existing local grace, and closes owned processes.

On Runtime crash, capacity and latency observations vanish. Canonical CLs and
existing returned-control markers retain exactly their prior meanings. Restart
begins conservatively with one warm process and must earn capacity again through
new locally chosen attention. No durable RUNNING, PROCESSING, worker, lease,
autoscaling, success, failure, or completion state exists.

## Conformance

The complete dependency-equipped Docker suite passes: **125 tests**. New
vectors prove arrival alone cannot grow capacity, cheap adapter calls do not
earn growth, slow pressure grows within the bound, idle attention sheds back to
one, and the earlier bounded/crash/no-running-state vectors continue to hold.
Compilation and whitespace checks pass.

## Verdict

Elastic capacity earns an experimental place, but not a universal default.
Serial remains the default. Fixed bounds remain the clearest choice for known,
continuously slow workloads. Elastic capacity is useful for intermittent slow
bursts where retaining the fixed pool's idle memory would be wasteful.

The architectural result is stronger than the throughput result: PORTER does
not scale from incoming demand signals. An already-attentive Host changes its
own bounded local machinery only after observing that its chosen attention is
under useful pressure. Arrival remains silent and powerless.

The one next experiment is **Elastic Opportunity Stability under Mixed
Latency**: determine whether a single recent slow call is too weak a signal when
cheap and slow Kinds are interleaved, and whether a small process-local evidence
window can prevent capacity oscillation without interpreting Kind, adding
fairness semantics, or persisting scheduler state.
