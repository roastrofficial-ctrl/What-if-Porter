# PORTER Non-Blocking Adapter Capacity Acquisition Check

Status: experiment complete, 2026-08-21.

This experiment asks whether an already-attentive elastic Runtime can prepare a
new adapter lane without pausing completion reaping, ordered CL publication, or
shutdown. A starting adapter has no Package identity, custody, correspondence,
worker assignment, or durable scheduler identity. It is only transient local
resource acquisition.

All frozen PORTER and Host adapter semantics remain unchanged.

## Accounting rule

The opportunity maximum now covers three mutually exclusive forms of local
commitment:

```text
published offers awaiting adapter control
+ one canonical publication in progress
+ adapter acquisitions in progress
≤ configured opportunity maximum
```

An acquisition reserves capacity before its startup future is submitted. The
reservation cannot be used for Collection or an adapter offer until readiness
has been validated through the unchanged `PORTER-HOST-ADAPTER/1` handshake. On
success it becomes an available adapter; on failure or cancellation it simply
vanishes.

Available idle adapters are resources but not outstanding opportunities. A
starting adapter is counted because it consumes the future lane and process
budget before it becomes available. Repeated visits cannot exceed the maximum
by accumulating starts behind active offers.

## Asynchronous acquisition

The old growth path called the adapter factory directly inside `visit()`. The
new path submits Package-free acquisition to the existing bounded local
executor and immediately returns to the attention loop. Later visits reap one of
three operational outcomes:

- `GROW`: readiness succeeded and the adapter enters the available pool;
- `FAILED`: no adapter exists and the reservation is released;
- `CANCELLED`: shutdown won the race and any late adapter is closed.

These events exist only in process memory. They are not journal facts, recovery
state, or application observations. The factory receives no Package,
Collection, dispatch, Kind, or candidate identity.

A failed acquisition observes a configurable local retry cooldown (default one
second). An early conformance vector showed that immediate re-evaluation could
otherwise retry in the same pressure loop, turning a broken executable into a
process/error storm. The cooldown is also forgotten on restart.

## Cancellation and shutdown

Asynchronous work is useful only if it can actually stop. Adapter startup now
accepts a process-local cancellation event while waiting for the readiness
line. It checks that event at short intervals, closes stdin, terminates or kills
the owned subprocess using the existing grace behavior, and raises a local
startup-cancelled error.

Shutdown sets the shared acquisition cancellation event before closing active
lanes. Futures which finish after local abandonment have a callback that closes
any adapter they managed to create. A real subprocess conformance vector starts
an adapter which never announces readiness and confirms cancellation terminates
the startup thread and child promptly.

If the Runtime process is killed outright, the in-memory reservation and
evidence disappear. Normal process ownership terminates the child environment;
restart begins at the configured initial single adapter and must earn growth
again.

## Responsiveness result

A controlled 45 ms adapter factory isolates the decision call itself:

| Acquisition | Attention call |
|---|---:|
| Synchronous | 49.696 ms |
| Asynchronous | 0.099 ms |

The attention-loop growth action became roughly **502x faster**. The actual
startup still took 48–56 ms; it simply ceased to occupy the choosing thread.
During a blocked startup, another completed offer was reaped while the
reservation remained in progress.

## Workload result

All workloads use ordered canonical publication, stable elastic evidence, a
maximum of four, and modeled 45 ms starts.

| Candidates | Adapter wait | Synchronous drain | Asynchronous drain | Async max visit |
|---:|---:|---:|---:|---:|
| 100 | 10 ms | 2.156 s | 2.295 s | 148.068 ms |
| 100 | 100 ms | 3.958 s | 3.935 s | 134.324 ms |
| 20 | 1,000 ms | 5.468 s | 5.472 s | 43.535 ms |

Acquisition is not a throughput optimization. The 10 ms run was 6.4% slower,
the 100 ms run 0.6% faster, and the one-second run effectively identical. At
short waits, executor scheduling and filesystem variation are larger than the
removed startup stall. The result earns itself on responsiveness and bounded
resource semantics, not on drain speed.

For the one-second shape, maximum visit duration fell from 81.095 to 43.535 ms
while total drain stayed the same. In shorter shapes, canonical publication and
local filesystem work still dominated the largest individual visit, which is
why their maximum-visit numbers do not directly expose the isolated 50 ms
improvement.

Every workload peaked at four adapters and at most four combined offers,
publications, and starts. Raw data is in
`benchmarks/results/nonblocking-acquisition.json`.

## Failure and crash shapes

Conformance establishes:

- startup does not block a later completion reap;
- starts count against the same opportunity maximum;
- a failed start creates no CL and changes no Package responsibility;
- failure releases only operational capacity and observes the retry cooldown;
- shutdown cancels an unready real adapter process;
- a late successful adapter is closed rather than admitted after shutdown;
- no starting, capacity, assigned, pending, worker, running, or processing file
  exists;
- restart inherits neither starting capacity nor latency evidence;
- the CL-before-offer recovery correction and all earlier phase-separation,
  mixed-latency, arrival, and crash vectors continue to hold.

## Configuration

Elastic acquisition is automatic whenever `--elastic-capacity` is selected.
The operational failure cooldown may be chosen with:

```text
--elastic-acquisition-retry-ms 1000
```

Serial execution and fixed pre-warmed pools do not acquire capacity dynamically
and are unchanged.

## Verdict

Non-blocking acquisition earns itself, narrowly and honestly. It does not make
applications complete faster. It prevents a justified local resource decision
from freezing the mechanism that observes control returns, orders truth
publication, and responds to shutdown.

The semantic result is clean: capacity preparation may be concurrent because it
changes no PORTER truth. It is bounded alongside real opportunities precisely
because it consumes the Host's finite ability to expose them later.

The one next experiment is **Canonical Recovery Frontier under Large History**:
determine whether startup can avoid reparsing every historical CL using only
disposable, auditable recovery progress while canonical facts remain the sole
authority and any missing or suspect frontier forces a complete reconstruction.
