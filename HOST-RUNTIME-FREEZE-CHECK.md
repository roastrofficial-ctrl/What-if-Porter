# PORTER — Host Runtime Contract Freeze Pressure Record

## Verdict

`PORTER-HOST-RUNTIME/1` and `PORTER-HOST-ADAPTER/1` are **FROZEN**.

The experiment removed adapter control over attention cadence and truth-grade
durability from expendable telemetry. It added a bound to local adapter control
output, not new application meaning. One unchanged Runtime now supports three
genuinely different Hosts:

- PHP/Laravel Find Me, which owns MailWeb continuation and later ROUNDS;
- Python HarmonicDB, which owns HDBE effects, recovery and Return Lodgement;
- tiny Python `TINY-TRANSFORM/1`, which records a digest/transformation, normally
  never Returns, and may lodge related or unrelated correspondence much later.

The Runtime source contains no branch for any of them. Find Me and HarmonicDB
application code did not change.

The lesson actually earned is:

> **A useful isolated Host needs a locally chosen opportunity to look, take
> custody, and expose recoverable correspondence. It does not need generic
> machinery to know whether anything useful happened next.**

## Responsibility subtraction

| Existing responsibility | Classification | Freeze result |
|---|---|---|
| canonical candidate validation | PORTER semantic necessity | survived |
| Collection before offer | PORTER semantic necessity | survived |
| recover CL after interrupted lifecycle | Host lifecycle necessity | survived |
| bounded visit | Host lifecycle mechanism | survived as policy input, not batch semantics |
| configured Kind interest | Host attention policy | survived as opaque local filter |
| inspection cadence | deployment/operator policy | Runtime mechanism obeys configured cadence |
| adapter-proposed `next_visit_ms` | application convenience | removed from Runtime interpretation |
| idle sleep | implementation convenience | retained by Python, excluded from contract |
| warm adapter process | implementation convenience | retained by Python, excluded from contract |
| candidate lexical order | laboratory accident | excluded from contract |
| adapter control return | Host lifecycle observation | survived, explicitly nonsemantic |
| durable returned-control marker | operational replay suppression | survived; loss permits duplicate opportunity |
| durable telemetry fsync | laboratory accident | removed |
| Return handling | application policy | never entered Runtime |
| application retry/timeout/error meaning | application/deployment | explicitly excluded |
| shutdown signals and grace | deployment/implementation | only between-offer semantics frozen |

No generic `PROCESSED`, `HANDLED`, `DONE`, `FAILED`, `RETRYING`, `COMPLETED` or
`ACKNOWLEDGED` state was added. Internal `handled` counters were renamed
`dispatched` because the old word claimed more than Runtime knew.

## What Runtime knows

Runtime knows candidate identity and opaque Kind, whether canonical AC validates
them, whether CL already exists, the complete Collection it established or
recovered, whether it offered that Collection, and whether local adapter control
returned. It does not know payload meaning, application start/effect/commit,
whether an effect should be retried, whether a Return was drafted or lodged, or
whether a journey is complete.

Collection remains special but narrow:

```text
Host chooses attention
  → candidate lookup
  → canonical AC/CL validation
  → CL durability threshold
  → Package recoverable in Host custody
  → adapter offer
```

Crash immediately after CL leaves Host custody and no application assertion. A
later Runtime may offer the same immutable Collection. Crash after adapter entry
is deliberately ugly: the application may or may not have acted. Its own facts
decide recovery; Runtime does not.

## Adapter failure and malice

- immediate exit/throw: Runtime interaction fails operationally; CL remains;
- malformed or wrong-dispatch output: rejected; no returned-control marker;
- output beyond 65,536 characters: bounded and rejected;
- hang: the serial Python implementation waits indefinitely; operator kill uses
  ordinary crash recovery; no generic timeout or FAILED fact appears;
- crash after effect, Return draft or Return Lodgement: application-owned records
  decide later behaviour exactly as before;
- no Return: valid indefinitely;
- later Return: independent later Lodgement;
- unrelated or multiple outbound Packages: independent ordinary Lodgements.

The adapter is robustness-untrusted but not sandboxed. A same-privilege process
with direct writable IPC access can attack local files; preventing that belongs
to deployment isolation, not this data contract. Adapter output cannot mutate
the Collection object held by a separate Runtime process or manufacture canonical
truth through the control channel.

## Attention, batching, ordering and shutdown

Kind selection belongs to Host-local configuration. It narrows attention without
becoming `kind → handler`; one adapter receives all configured opportunities and
owns interpretation. Cadence and idle policy belong to deployment/operator.
Adapters may still emit legacy `next_visit_ms`, but Runtime ignores it.

Batch size is a cap on independent offers. In the ten-item crash vector, the
fifth Package crossed CL before its adapter crashed: five CL facts remained,
four returned-control observations remained, and five Packages remained Porter
custody. Restart offered the one ambiguous Collection plus the five uncollected
Packages. There is no batch transaction or rollback.

Ordering is unspecified. Current SQLite/package sorting is implementation
determinism, not PORTER sequence. One-shot, intermittent, continuous and dormant
Hosts are all legitimate. SIGTERM/SIGINT stop cleanly between offers. During a
blocked adapter call, graceful shutdown waits; forced termination recovers from
the existing CL boundary.

## Third Host and networking

The tiny Host required configuration and an adapter only—zero Runtime changes.
Its normal journey produced one AC, one CL, one application fact and zero
Returns. A second, later execution lodged a correlated `tiny.return`; another
trial lodged unrelated `tiny.notice` without `in_reply_to`.

The Docker third-Host journey ran with `network_mode: none`, no TCP listener and
no Ethernet interface. Linux exposed inert tunnel devices but no application
listener. The same local Runtime/adapter contract completed one useful
transformation. No nginx, Apache, WSGI, PHP-FPM listener, reverse proxy or Host
application TCP listener appeared.

The real rebuilt Butterfly journey also completed unchanged:

```text
Postbox → Porter → networkless Find Me Runtime
  → HDBE Package PKG-ab388260f5d8c44c5f9203409a083eb6
  → Ticket CT-c3d67544fb64fadf448921b306f3d623
  → Lodgement LG-ddd34191634264b9ecad4c5325f48754
  → networkless HarmonicDB Runtime
  → later Find Me attention
  → SERVED WITHOUT A WEB SERVER
```

In this architecture a Porter is the network participant; a Host Runtime is
local attention machinery; an application owns meaning; the Host is the isolated
computational environment. Calling all four a “server” hides the useful boundary.

## Backlog and slow-adapter pressure

Docker/Linux measurements used a trivial in-process adapter and canonical CL per
item. Operational telemetry was non-durable; returned-control state remained
durable.

| Candidates | Batch | Drain | Throughput | Inspection median | CL median | Runtime dispatch median |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1 | 0 ms | — | — | — | — |
| 1 | 1 | 5.815 ms | 171.96/s | 0.181 ms | 4.585 ms | 0.094 ms |
| 100 | 100 | 439.207 ms | 227.68/s | 5.450 ms | 3.029 ms | 0.024 ms |
| 1,000 | 100 | 11.316 s | 88.37/s | 5.538 ms | 10.498 ms | 0.028 ms |
| 10,000 | 100 | 847.400 s | 11.80/s | 6.502 ms | 82.315 ms | 0.034 ms |

At 1,000, batches 1/10/100 drained in 11.135/10.573/10.911 seconds. Batch size
barely matters because each CL is independent. Empty attention after the drains
remained 0.056–0.135 ms. Peak RSS reached 51,820 KiB after the 10,000-item run.

The 10,000 curve reveals severe large-directory Collection cost, not Runtime
meaning leakage. It does not invalidate the contract; it makes throughput an
implementation pressure. No concurrency or relaxed canonical durability was
added.

| Adapter delay | Items | Drain | Dispatch median |
|---:|---:|---:|---:|
| 10 ms | 10 | 161.892 ms | 10.991 ms |
| 100 ms | 10 | 1.079 s | 101.087 ms |
| 1 s | 10 | 10.083 s | 1.001 s |
| 10 s | 1 | 10.010 s | 10.001 s |

A slow adapter blocks unrelated opportunities and shutdown in the single-threaded
reference implementation. It does not damage custody or force application
semantics. This is earned scheduling pressure, intentionally unsolved here.

## Telemetry and durability

Telemetry may say Runtime/adapter ready, visit began/ended, candidate selected,
dispatch began, control returned, timing and shutdown requested. It never means
processed, succeeded, failed or complete. Deleting the journal leaves AC, CL,
returned-control state and application facts unchanged. Because it is expendable,
the reference journal flushes but no longer `fsync`s each line.

The separate returned-control marker affects only whether the reference Runtime
needlessly re-offers a Collection. It says exactly `ADAPTER_RETURNED_CONTROL`.
It is not canonical or application evidence; loss can cause duplicate opportunity.

## Conformance and reproducibility

The final rebuilt Docker PORTER suite passed all 115 tests, including 15 focused
Runtime tests and the malformed/oversized adapter controls. The real Find Me journey and networkless
third-Host journey both passed. Existing Runtime adapters and PORTER semantics
remained unchanged.

Raw pressure is in `benchmarks/results/host-runtime-freeze.json`. Reproduce with
`benchmarks/host_runtime_freeze.py`; the isolated third journey is
`benchmarks/third_host_journey.py`.

The contract is genuinely small and independently implementable: chosen local
attention, canonical validation, Collection, local offer, optional operational
control return—and explicit ignorance of meaning.

## Exactly one next experiment

**Host Runtime Opportunity Scheduling under Slow and Large-Directory Pressure.**

Test whether independent Collections can be offered with bounded isolation and
responsive shutdown when one adapter is slow, while preserving Host-chosen
attention, per-Package CL thresholds, no ordering promise, no batch transaction,
and no application retry/disposition semantics. This is the first experiment in
which concurrency may be put on trial; it is not pre-approved as the answer.
