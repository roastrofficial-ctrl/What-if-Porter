# PORTER — Indexed Local Attention Check

## Verdict

Indexed Local Attention succeeded.

The optimisation made a Host's chosen inspection substantially cheaper without
making Package arrival causally powerful. Canonical PORTER facts are unchanged.
The projection is disposable. Neither application adapter changed. Attention
policy, ROUNDS, batching and single-threaded execution remain unchanged.

The historical lesson is:

> **An index may tell a Host where to look without deciding when the Host looks.**

This is the first deliberate PorterNet performance maturation that made the
system less accidental without weakening the Host Isolation Principle.

## What was expensive

The former `HostRuntime.candidates()` enumerated every `inbox/PKG-….json`, read
and decoded every complete Package, and only then compared its carriage-visible
Kind with the Runtime allow-list. Discovery therefore depended on all current
Porter custody and all Package bytes, even when nothing was relevant.

Instrumentation isolated discovery from Collection and adapter dispatch. At
10,000 Packages, an empty warm lookup took 2,507.174 ms median and finding one
relevant Package took 2,174.287 ms. Finding 1,000 took 2,242.420 ms: cost was
almost entirely N, not k.

## Representation tested

`PORTER-CANDIDATES/1` is one local SQLite projection containing exactly:

```text
Package identity → opaque Kind
```

The Package identity is the primary key. Kind has an index used by Runtime
allow-lists. The projection uses one persistent inode rather than another file
per Package. It contains no payload, application summary, Ticket copy, priority,
success state or attention instruction.

SQLite was not selected merely as a familiar database. The alternatives were
attacked first:

- scanning the existing inbox is truthful but remained Θ(N) and read payloads;
- per-Kind directories or per-Package links avoid JSON reads but add roughly one
  inode per candidate and retain directory-enumeration cost;
- rewriting a compact JSON manifest uses one inode but makes every AC and CL
  mutation Θ(N), enlarges crash windows and creates large repeated writes;
- an append-only manifest makes publication cheap but requires replay,
  compaction and duplicate/stale filtering during the attention path.

The small embedded table gave indexed selection, a uniqueness constraint,
transactional projection mutation and one inode. It does not replace the
filesystem evidence model.

## Truth and lifecycle

No new immutable fact or PORTER threshold exists.

```text
canonical AC exists and no canonical CL exists
    → candidate row may exist

canonical CL exists
    → candidate row may disappear
```

Canonical `acceptances/PKG-….json` and `collections/facts/CL-….json` plus the
existing Package-to-Collection association reconstruct the complete projection.
Truth reconstructs projection; projection never reconstructs truth.

Acceptance writes AC first, then its existing inbox projection, then the
candidate row. Collection writes CL first, materialises Host custody, then
removes the candidate. A projection error may make an operation report an
interruption after the canonical threshold; it cannot roll truth back.

Each selected row is checked against its canonical AC before Collection. An
unknown Package or wrong Kind is removed and cannot cause Collection. A stale
candidate whose CL already exists can produce only the existing deterministic
Collection identity; it cannot create a second CL.

## Before and after

Times are warm medians in milliseconds. Baseline used five repetitions because
the 10,000-item full scan itself took minutes; indexed results used 25.

| Relevant / total | Current scan | Indexed |
|---|---:|---:|
| 0 / 0 | 0.139 | 1.137 |
| 0 / 10 | 6.512 | 1.061 |
| 0 / 1,000 | 903.008 | 1.563 |
| 0 / 10,000 | 2,507.174 | 0.927 |
| 1 / 10 | 4.652 | 1.213 |
| 1 / 1,000 | 220.871 | 2.455 |
| 1 / 10,000 | 2,174.287 | 2.005 |
| 10 / 10,000 | 2,182.587 | 5.503 |
| 100 / 10,000 | 2,229.905 | 25.946 |
| 1,000 / 10,000 | 2,242.420 | 246.629 |

Empty indexed attention was effectively independent of N. Candidate discovery
is an indexed lookup plus O(k) canonical AC validation. One candidate among
10,000 required one projection file and one canonical AC read rather than
10,000 Package reads. At high k, canonical validation correctly becomes visible.

The indexed mechanism imposes about a 1 ms fixed cost at zero state. The prior
scan is therefore faster only in the uninteresting empty-directory microcase.

## Transition cost

| Transition | Without candidate maintenance | Indexed | Difference |
|---|---:|---:|---:|
| AC median | 2.108 ms | 3.462 ms | +1.354 ms / +64.2% |
| CL median | 20.868 ms | 20.943 ms | +0.075 ms / +0.4% |

The AC comparison includes the existing canonical AC and inbox fsyncs. Indexed
publication adds one fully synchronous SQLite transaction. CL already pays its
canonical and Host-custody durability costs, so deletion was lost in that larger
cost on this implementation.

Looking became dramatically cheaper by making accepted responsibility about
1.35 ms more expensive. Refused correspondence pays nothing because it never
crosses AC.

## Storage and reconstruction

| Candidates | Projection bytes | Persistent inodes | Cold rebuild |
|---:|---:|---:|---:|
| 1,000 | 73,728 | 1 | 3,807.045 ms |
| 10,000 | 602,112 | 1 | 44,509.975 ms |

At 10,000 this is about 60 bytes per candidate. SQLite rollback-journal files
may exist transiently during a mutation but no per-candidate inode survives.
100,000 was not tested: fixture construction and the observed 10,000-file
canonical scan cost made it unlikely to add architectural information.

Cold reconstruction is deliberately O(canonical history) and was painfully
slow on this filesystem. That does not contaminate steady-state attention.
Porter startup reconstructs from AC minus CL; malformed, truncated, missing or
wrong-version state rebuilds on the next chosen inspection. Explicit local
reconciliation detects missing, stale and wrong rows. No periodic reconciliation
was added because repeatedly scanning history would recreate the problem; Porter
restart and explicit disaster repair are sufficient for this projection's
current failure model.

## Crash and corruption matrix

The tests interrupted or corrupted every meaningful boundary:

| Case | Result |
|---|---|
| AC exists before candidate publication | restart rebuilds the missing row |
| candidate published, then crash | AC remains authoritative; row is usable |
| CL exists before candidate removal | stale row is harmless; restart removes it |
| candidate removed, then crash | CL and Host custody remain authoritative |
| projection deleted | rebuilt from uncollected AC |
| malformed/truncated database | rejected and rebuilt |
| stale schema version | rejected and rebuilt |
| unknown Package row | rejected against absent AC and removed |
| wrong Kind | rejected against canonical AC and removed |
| duplicate Package | primary-key uniqueness collapses it |
| missing candidate | explicit reconciliation restores it |
| candidate settles after inspection | repeated Collection returns the one existing CL |
| Runtime dies after identifying work | AC/candidate remain; no Collection occurred |
| Runtime dies after CL before operational return | existing Host Runtime recovery redelivers the exact CL |

Projection damage never created, changed or deleted AC or CL. Repair never
starts an adapter and cannot create application execution.

## The causality proof

The real HarmonicDB Host Runtime was stopped. Before lodgement, its recipient
Porter held two candidates and 27 CL facts. Networkless Find Me then lodged real
HDBE Package `PKG-567160c3b36fdf587b516d67293c5544`.

After waiting:

- the candidate count was three;
- the new row contained only the Package identity and `hdbe.call` Kind;
- the CL count remained 27;
- the HarmonicDB container remained `exited false`;
- no Runtime or adapter process existed;
- no Round or application effect occurred.

No watcher, inotify subscription, blocking Porter-written read, socket, pipe,
signal, callback, event bus or condition variable exists. The projection is a
passive file. Porter does not know the Runtime process identity and has no code
path that starts it.

Only the independent local command `docker compose start harmonicdb` caused Host
attention. Its first visit queried `PORTER-CANDIDATES/1` in 1.264 ms, explicitly
created canonical Collection `CL-abe5fbc6a22c41079f2b4d780985889c`, dispatched
the unchanged HDBE adapter, lodged a Return, and removed the candidate.

Arrival prepared knowledge. Local policy caused attention.

## Real applications

A fresh unchanged Find Me journey again completed:

```text
Postbox → Porter → networkless Find Me
        → Porter → networkless HarmonicDB
        → Return → later Find Me Round
        → SERVED WITHOUT A WEB SERVER
```

HDBE Package `PKG-3390f688fef2972135e3894154f2778c` returned through Round
`RD-6e2c07a17705a7d724787d7b68213d45` and Collection
`CL-27ade1780ff5c9c3f28790a11bc1910d`.

Real indexed lookup observations were 1.257 and 0.479 ms in Find Me, and 0.789
ms in HarmonicDB. Runtime observations explicitly name `PORTER-CANDIDATES/1`;
Collection remains the canonical PORTER operation.

Find Me still chose 10 ms attention during active MailWeb revisit and 250 ms
after completion. HarmonicDB still chose 50 ms. The index did not change those
values, initiate a Round or inspect a MailWeb document. Both network tables had
headers only, Docker reported zero Host network I/O, and Find Me contained only
the Runtime and its warm PHP adapter. No Host listener or webserver exists.

## Idle behaviour

Over ten idle seconds:

| Host | Runtime RSS | Voluntary switches | Non-voluntary | Journal growth | CPU point sample |
|---|---:|---:|---:|---:|---:|
| Find Me | 16,956 KiB | +39 | +0 | 0 bytes | 0.18% |
| HarmonicDB | 15,192 KiB | +191 | +0 | 0 bytes | 0.78% |

Wakeups remain functions of the unchanged application attention cadences. Empty
visits still do not grow the journal. SQLite open/query overhead raises the
small-state HarmonicDB point sample relative to the preceding 0.31% observation;
the improvement is earned at scale, not free at tiny state.

## Security and privacy

Candidate publication occurs inside admitted `Porter.deposit` only after
Introduction/standing, proof, Kind, size, expiry and custody-budget checks and
after canonical AC. Existing 10,000-attempt unknown-sender and compromised-old-
capability tests compare the entire recipient file set before and after. They
created zero additional candidate entries, files or bytes. Oversized, expired,
wrong-Kind and proofless correspondence likewise never reaches publication.
Invalid native frames never enter `deposit`.

The index is local to the recipient Porter. It reveals Package identity and Kind,
which that Porter already legitimately knows from the carriage-visible envelope.
It stores no payload, sender-derived summary, application result or attention
policy. Local filesystem access remains a deployment trust boundary; the index
is not a query service or metadata API.

## What remained unchanged

- canonical PORTER/1–1.5 facts and thresholds;
- `PORTER-HOST-ADAPTER/1` and both application adapters;
- Find Me MailWeb semantics, continuation and ROUNDS;
- HarmonicDB HDBE semantics, effects and recovery;
- batch 10 for Find Me and batch 25 for HarmonicDB;
- single-threaded Runtime execution;
- Host-controlled attention cadence;
- native carriage;
- networkless, listener-free Hosts.

The complete installed suite passed 97 tests, including hostile admission,
succession, ceremony, native carriage, rendezvous continuity, Collection,
Runtime crash and candidate corruption cases. PHP lint and Find Me health passed.

## What became elegant and difficult

The elegant result is that the projection needs less knowledge than expected.
Package identity plus opaque Kind is sufficient. Tickets, Returns, standing and
expiry require no copied state because canonical AC/CL and Runtime policy already
resolve them.

The difficult result is the durability asymmetry. A one-millisecond steady-state
lookup is purchased with a second durable local transition at AC and a 44.5
second worst-case rebuild at 10,000 on this filesystem. Cross-UID shared-volume
metadata also had to remain best-effort; chmod is not a correctness threshold.

The system is nevertheless substantially better where attention pressure
exists: empty 10,000-item visits improved by roughly 2,700× and finding one by
roughly 1,084×, with one inode and no causal backchannel.

## Exactly one next experiment

The next experiment is **Candidate Projection Durability**.

It should ask whether grouped/checkpointed local projection maintenance can
reduce the measured +64.2% AC cost and 44.5-second 10,000-item disaster rebuild
without adding canonical facts, per-candidate inodes, notification, weaker
fsync semantics or application coupling. Runtime concurrency and broader
PorterNet product work remain explicitly out of scope.
