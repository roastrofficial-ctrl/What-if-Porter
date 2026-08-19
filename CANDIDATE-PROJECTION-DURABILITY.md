# PORTER — Candidate Projection Durability Pressure Record

## Verdict

Candidate Projection Durability succeeded.

`AC` still crosses exactly the same canonical durability threshold. The
candidate projection now uses grouped SQLite WAL durability (`synchronous=NORMAL`,
checkpoint every 100 pages) and retains its connection across mutations. A
candidate mutation is transactionally visible to a running Porter, but its
latest WAL tail need not survive machine power loss. Machine loss also restarts
Porter, and Porter reconstructs the whole projection from canonical AC minus CL
before becoming usable. No second acceptance fact, clean marker, generation or
high-water mark was introduced.

The historical lesson actually earned is:

> **Truth should be expensive enough to deserve belief. Projection should be
> cheap enough to lose—but loss must force an encounter with truth before the
> projection can be trusted again.**

The system is better. Candidate maintenance moved from a 64.2% historical AC
tax to 1.6% in the controlled transition run, while warm empty attention became
cheaper. The price is explicit: disaster recovery still costs about 43 seconds
at 10,000 facts on this filesystem.

## Promise and ordering

The representation remains `PORTER-CANDIDATES/1`:

```text
Package identity → opaque Kind
```

Its promise is deliberately weaker than AC:

- a row is a hint and must be validated against canonical AC and CL;
- an absent row cannot make accepted custody historically false;
- a stale row cannot make a second Collection;
- update failure invalidates the entire projection instead of leaving a
  plausible-looking partial view;
- Porter startup rebuilds before service; a chosen inspection rebuilds an
  absent, malformed, corrupt or wrong-version projection;
- deleting the database and every piece of projection metadata loses no truth.

The write path remains:

```text
native admission
  → canonical AC construction and durable publication
  → inbox projection
  → candidate transaction
  → operation returns
```

Candidate work never precedes admission or AC. Arrival still cannot start a
Runtime, adapter, Round or application action.

## Why it was expensive

The old candidate path opened SQLite, checked schema and performed a
rollback-journal transaction with truth-grade synchronous durability for every
mutation. Connection setup, journal creation/removal, locking and filesystem
barriers dominated the tiny two-column row update.

Instrumentation of the grouped 500-accept path measured these medians:

| Component | Median | p95 | p99 |
|---|---:|---:|---:|
| canonical AC | 1.163 ms | 1.727 ms | 5.651 ms |
| inbox projection | 1.080 ms | 1.569 ms | 4.323 ms |
| candidate projection | 0.448 ms | 0.800 ms | 2.492 ms |
| complete deposit | 2.720 ms | 4.189 ms | 14.133 ms |

The component probe includes Python calls and locking around each layer; the
interleaved end-to-end transition comparison below is the fair strategy result.

## Strategies tested

| Strategy | AC median | AC p95 | AC p99 | Candidate barrier | Loss window |
|---|---:|---:|---:|---|---|
| no index | 1.974 ms | 5.043 ms | 8.563 ms | none | not applicable |
| synchronous DELETE/FULL | 2.935 ms | 6.593 ms | 9.636 ms | every mutation | none after return under SQLite/filesystem claims |
| transactional DELETE/OFF | 2.586 ms | 2.987 ms | 4.209 ms | none | recent transaction/filesystem state |
| grouped WAL/NORMAL | 2.006 ms | 2.557 ms | 3.599 ms | amortised checkpoint | WAL since last durable checkpoint |

The grouped median adds 0.032 ms, or 1.6%, over no index in this 200-transition
run. Candidate-specific forced durability barriers per ordinary AC are zero;
canonical AC's existing file and directory durability remains unchanged.
SQLite may sync WAL during its grouped checkpoint policy.

Direct interleaved candidate-only measurements also favoured grouped WAL. On a
noisy local filesystem its insertion median was 1.624 ms, against 4.734 ms for
FULL and 4.557 ms for OFF rollback journalling. Journal lifecycle and retained
WAL state, not merely `fsync`, were material.

Transactional relaxed mode was rejected as the default. It removed barriers but
did not amortise rollback-journal lifecycle and gave a less useful crash model.
Canonical-tail repair was also rejected: Package UUIDs and timestamps are not a
canonical total order, while a durable completeness cursor would become AC2 in
all but name.

## Completeness and starvation

Completeness is not recorded as a new fact. It is an invariant of the current
Porter lifecycle:

```text
Porter startup rebuilt AC − CL
and
every later AC mutation committed to the live projection
or invalidated the whole projection
```

A warm Host restart does not rebuild: committed WAL is already visible to the
continuously running Porter. A Porter restart always reconstructs before it can
serve a Host. A live connection/database error removes the projection; the next
chosen inspection reconstructs it. Thus the two practical routes to missing
rows—machine/Porter loss or detected live update failure—cannot silently
starve work.

A coherent old database image substituted behind a still-running Porter cannot
be distinguished from a complete projection without rescanning history. That
is outside the claimed ordinary failure route: filesystem rollback/power loss
also loses the Porter process. The test nevertheless installed a partial old
image, observed its incompleteness, then proved Porter restart restored all five
Packages. No power-loss guarantee beyond the tested approximations is claimed.

No generation, dirty epoch, checkpoint marker or high-water fact exists.
Projection absence is the only repair signal stored by the projection itself.

## Crash and corruption matrix

| Boundary or damage | Canonical result | Projection/next inspection result |
|---|---|---|
| before AC | no AC or candidate | nothing discoverable |
| after AC, before candidate | AC survives | Porter restart reconstructs row |
| during candidate transaction/connection loss | AC survives | projection invalidated; chosen inspection rebuilds |
| committed WAL before checkpoint | AC survives | warm Porter sees row; power-loss approximation may lose tail, restart rebuilds |
| several uncheckpointed mutations | all ACs survive | removed WAL tail lost three rows; restart recovered all five |
| during checkpoint | AC unaffected | invalid database is rebuilt from history |
| after checkpoint | AC and candidate represented | normal indexed inspection |
| after CL, before removal | one CL | stale row is discarded and cannot duplicate CL |
| after removal, before checkpoint | one CL | lost deletion can only resurrect a harmless stale row |
| database deleted/truncated/corrupt | AC/CL unchanged | absence/error causes reconstruction |
| stale schema or WAL | AC/CL unchanged | old sidecars discarded; single-file replacement published |
| many stale rows before one live row | CLs win | Runtime purges/refills until live candidate is found |

Reconstruction builds a temporary DELETE-journal database in one transaction,
closes old readers/writers, discards old WAL sidecars, and atomically replaces
the complete file with one directory publication. An interruption therefore
leaves the previous projection or no usable replacement, not half a new one.

Stale rows remain deliberately boring. Eager grouped deletion was retained
because it is cheap and prevents corpse accumulation; no compactor or daemon was
earned. Runtime canonical validation remains the safety boundary.

## Rebuild pressure

| Candidates | Total | Canonical scan | Construction | Publication | Bytes | Inodes |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 134.858 ms | 128.899 ms | 4.348 ms | 0.980 ms | 24,576 | 2 |
| 1,000 | 3,758.926 ms | 3,738.630 ms | 15.060 ms | 4.249 ms | 73,728 | 2 |
| 10,000 | 42,989.069 ms | 42,964.957 ms | 20.715 ms | 2.403 ms | 602,112 | 2 |

At 10,000, 99.94% of reconstruction was enumerating and decoding canonical AC
and checking existing Package-to-CL associations. Building all rows in one
disposable transaction took 20.7 ms and publication took 2.4 ms. Per-row durable
reconstruction was accidental and has been removed; examining canonical history
remains fundamental under the present evidence layout.

The projection uses one database plus one fixed lock after cold reconstruction.
Grouped steady state may add fixed `-wal` and `-shm` files: four inodes total,
never one inode per candidate. The run recorded process peak RSS of about 31 MiB
at 10,000 attention items. It does not yet count kernel filesystem operations or
separate CPU from filesystem wait, so no invented figures are reported. 100,000
was not informative while the canonical scan remains this dominant.

## Attention remains indexed

| Relevant / 10,000 | Median | p95 |
|---:|---:|---:|
| 0 | 0.295 ms | 0.313 ms |
| 1 | 1.338 ms | 2.123 ms |
| 10 | 6.002 ms | 13.325 ms |
| 100 | 26.701 ms | 27.626 ms |
| 1,000 | 259.162 ms | 303.092 ms |

Empty attention remains approximately fixed and finding k is dominated by k
canonical validations. This improves the preceding 0.927/2.005 ms zero/one
result without changing the conceptual Runtime request.

## CL, security and causality

CL truth is unchanged and still precedes candidate removal. The transition
benchmark's Collection figures were dominated by canonical Collection and
growing custody directories, so they are not a clean deletion delta; the
candidate-only grouped deletion median was 1.618 ms. Because stale rows are
harmless, deletion has weaker correctness pressure, but grouped eager deletion
was cheap enough to retain.

The hostile admission suite remained green: unknown/spoofed sender, wrong Kind,
bad proof, oversized Package, expiry and custody budget all stop before AC and
candidates; 10,000 strangers and 10,000 compromised-capability attempts create
no per-attempt recipient or candidate state.

Candidate maintenance is Porter-local preparation only. It contains no watcher,
callback, signal, socket or adapter reference. A stopped Runtime can accumulate
ACs and WAL mutations with no Round, CL or application effect. Starting the Host
independently performs the chosen inspection. Neither adapter changed;
attention cadence, ROUNDS, batching and single-threaded execution are unchanged.

The focused candidate/Runtime suite passed 22 tests; the hostile and custody
selection passed 37. Full local discovery ran 87 tests: 85 passed and two
native/rendezvous modules could not import the host's missing `cryptography`
dependency. Docker real-journey verification could not run because this
session's Docker escalation was denied by the execution usage limit. The prior
Find Me ↔ HarmonicDB journey remains the baseline, but is not mislabelled as a
fresh durability run.

## What surprised us

The elegant part was that no completeness fact was needed. Grouped loss and
Porter restart are naturally paired, while detected live failure turns a
possibly partial view into honest absence. A disposable projection can protect
itself by refusing to look complete.

The difficult part was atomic replacement in WAL mode. Replacing only the main
SQLite file allowed an old `-wal` sidecar to overlay stale schema on the new
inode. Reconstruction now uses a single-file database and removes old sidecars
before publication. The other difficult truth is that faster SQLite cannot
repair a 42.965-second canonical filesystem scan.

## Exactly one next experiment

**Canonical History Enumeration.**

Determine whether PORTER can enumerate AC and CL evidence for disaster
reconstruction without 10,000 small-file directory/read costs, while preserving
every canonical identity, threshold, replay and audit property. This is not a
candidate-cache experiment, database migration or productisation. Any catalogue
required for truth becomes a new canonical authority and must be rejected or
named honestly.
