# PORTER Host Runtime Opportunity Scheduling Check

Status: implementation and pressure check complete, 2026-08-20.

This experiment leaves `PORTER-HOST-RUNTIME/1` and
`PORTER-HOST-ADAPTER/1` frozen. It separates two problems which happened to
appear in the same pressure run: Collection publication was quadratic in
history size, while a serial Runtime could expose only one opportunity during a
slow adapter call. They have different causes and different remedies.

## Result

Canonical Collection publication no longer scans every previous CL to prove
that a new Package lacks one. A disposable Package-to-CL association is now
reserved before the unchanged atomic CL publication threshold. The association
cannot make Collection true: readers still require the named canonical CL fact.
Startup recovery repairs historical or interrupted projections once, after
which a Runtime can safely use direct association lookup.

For slow applications, the optional `BoundedOpportunityRuntime` offers at most
`N` independent opportunities through `N` unchanged, warm adapter processes.
The default remains the exact serial Runtime (`--max-inflight-offers 1`). No
Find Me, HarmonicDB, Tiny Host, Package, AC, CL, Return, Kind, or adapter-contract
semantics changed.

The experiment earns the Collection repair and an opt-in fixed opportunity
bound for known-compatible applications. It does **not** earn concurrency as a
default: with a zero-cost application, four concurrent filesystem publishers
are slower and consume substantially more CPU and idle memory.

## What an opportunity is

An opportunity begins when the locally active Runtime chooses a candidate and
starts establishing or recovering its CL for an adapter offer. It remains
outstanding until the adapter returns local control and the Runtime records the
existing non-canonical returned-control marker.

The configured bound covers both Collection publication in progress and an
offer awaiting control. Therefore a bound of four can create at most four new
CLs without control returns. There is no collected-but-not-offered work queue.
Arrival still cannot wake a Host or create capacity; a locally chosen Runtime
visit alone exposes opportunities.

## Why the large-directory run was quadratic

`collect_package()` previously called `find_collection()` for each new
Package. When no by-Package association existed—which is the normal state for a
new Package—the lookup parsed every canonical `CL-*.json` fact to establish
absence. Draining `N` new Packages therefore performed approximately
`1 + 2 + ... + N` historical CL inspections.

The prior 10,000-candidate run took 847.400 seconds, with 82.315 ms median CL
publication. With direct association after one startup recovery, the same
serial shape takes 21.110 seconds: 473.70 Packages/s and 1.908 ms median
CL-to-offer latency. That is a 40.1x drain improvement without scheduling.

Crash behavior remains monotonic:

- interruption after association reservation creates no CL and transfers no
  custody;
- retry may replace that disposable reservation and publishes exactly one CL;
- after CL publication, the reservation already names it;
- startup recovery still reconstructs collected, association, inbox, and
  candidate projections from canonical CL facts;
- standalone callers retain the conservative history scan by default.

## Scheduling model examined

The accepted experimental model is a process-local bounded pool:

- one warm adapter process per possible outstanding offer;
- one offer at a time per adapter instance;
- futures, adapter assignment, and the submitted set exist only in memory;
- Package selection and CL publication remain the Runtime's responsibility;
- each adapter sees the unchanged `PORTER-HOST-ADAPTER/1` JSON-lines exchange;
- adapter failure retires that instance and shrinks local capacity; the Runtime
  does not invent retry semantics;
- shutdown stops new offers, waits a local grace period, then may terminate
  owned adapter processes as an operational action.

`--batch-size` remains an inspection/selection cap. The independent
`--max-inflight-offers` option is the resource and semantic exposure bound.

Other models were rejected:

- A process per opportunity pays adapter startup repeatedly (Tiny measured
  about 45 ms) and discards the established warm-process advantage.
- Concurrent calls through one adapter process require multiplexing and
  application reentrancy that the frozen line protocol does not promise.
- Multiple Runtime processes preserve one canonical CL through locking, but a
  deterministic competition test produced two adapter offers for that one CL.
  This is semantically allowed duplicate exposure but a harmful scaling tool.
- A durable worker, RUNNING, PROCESSING, lease, claim, or completion state would
  confuse operational scheduling with PORTER truth and was not introduced.

## Pressure results

These Linux/Docker measurements use the canonical CL path and a controlled
adapter delay. `bounded-4` means four independent warm adapters and an
opportunity bound of four.

| Candidates | Adapter delay | Serial drain | Bounded-4 drain | Relative result |
|---:|---:|---:|---:|---:|
| 100 | 0 ms | 308 ms | 351 ms | 0.88x |
| 1,000 | 0 ms | 2.692 s | 4.134 s | 0.65x |
| 10,000 | 0 ms | 21.110 s | 51.131 s | 0.41x |
| 100 | 10 ms | 1.661 s | 646 ms | 2.57x |
| 1,000 | 10 ms | 13.984 s | 6.012 s | 2.33x |
| 10,000 | 10 ms | 140.365 s | 66.062 s | 2.12x |
| 100 | 100 ms | 10.635 s | 2.793 s | 3.81x |
| 1,000 | 100 ms | 106.480 s | 27.852 s | 3.82x |
| 10 | 1 s | 10.189 s | 3.035 s | 3.36x |

The 10,000 × 100 ms serial cell was deliberately not run: it would spend about
1,000 seconds confirming an already stable latency-dominated result. Raw data
for all executed cells is in
`benchmarks/results/opportunity-scheduling.json`.

The first control return is not materially earlier at 100 ms (107.805 ms serial
versus 111.578 ms bounded at 100 candidates), because serial already starts the
first opportunity immediately. The gain is that B, C, and D can progress while
A is slow. A gated test confirms that one indefinitely blocked adapter occupies
one slot without monopolising the remaining capacity.

Concurrency amplifies local filesystem contention. At 10,000 zero-delay items,
bounded-4 used 53.046 CPU seconds versus 7.356 serial and reduced throughput
from 473.70/s to 195.57/s. Scheduling therefore addresses application waiting;
it is not a substitute for the Collection fix.

## Idle and resource cost

Actual Tiny adapter subprocesses were observed for ten idle seconds:

| Warm adapters | Startup | Adapter RSS | CPU ticks | Context switches |
|---:|---:|---:|---:|---:|
| 1 | 45.226 ms | 15,816 KiB | 0 | 0 |
| 4 | 87.704 ms | 63,108 KiB | 0 | 0 |

The fixed pool is quiet but costs roughly four times the adapter memory. This is
why serial remains the safe default and higher capacity is explicit local
deployment policy. Find Me and HarmonicDB continue at one; Tiny controls the
concurrent shape without application-specific Runtime branches. No fairness or
priority scheme was earned: Kind remains opaque, ordering remains unspecified,
and a finite backlog progresses as capacity returns.

## Crash and restart meaning

The explicit crash vector holds four candidates with a bound of three:

```text
A: CL-A published, adapter offer outstanding
B: CL-B published, adapter returned control, marker durable
C: CL-C published, adapter offer outstanding
D: still in Porter custody
```

If the Runtime disappears, only futures and adapter assignment vanish. A and C
remain collected and may be offered again after recovery; B's returned-control
marker suppresses another offer while that disposable marker survives; D
remains the Porter's responsibility. Duplicate possibility is unchanged from
the frozen contract. No durable byte claims that A or C is running, failed,
complete, owned by a worker, or entitled to a retry.

## Conformance and real Hosts

The complete container suite passes: **122 tests**. New vectors cover the
strict opportunity bound, one hung offer with unrelated progress, competing
Runtimes, absence of durable running state, the crash shape above, association
reservation interruption, and one-time startup history recovery.

Rebuilt Find Me, HarmonicDB, and MailWeb/Postbox containers remained healthy.
The real MailWeb journey produced ticket
`CT-284e59e5bcb8941a70d437eaf841086b`; the earlier frozen end-to-end and
networkless Tiny Host proofs require no application or contract change.

## Decision

Keep the direct-association Collection repair. Keep serial one-warm-process
execution as the default. Retain bounded multi-process opportunity scheduling
as opt-in Host deployment policy when the application is known to tolerate
independent concurrent processes and its wait time dominates local publication
cost. Do not use multiple Runtime processes as a concurrency mechanism.

The one next experiment is **Host-Chosen Elastic Opportunity Capacity**: measure
whether a locally active Runtime can grow an opt-in adapter pool during observed
backlog and retire excess warm processes after local idleness, without allowing
Package arrival to wake it, changing the adapter contract, or creating durable
scheduler state. The pressure is specific: fixed capacity wins 2.1–3.8x for
slow adapters but four idle Tiny processes consume 63 MiB and cheap work becomes
slower under contention.
