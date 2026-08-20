# PORTER — Canonical History Enumeration Pressure Record

## Verdict

Canonical History Enumeration succeeded without changing canonical storage.

The experiment did **not** earn a catalogue, manifest, segment, completeness
cursor, new fact, or PORTER generation. `AC` and `CL` remain independent,
immutable JSON facts with their existing identities and durability thresholds.
The accepted change only replaces the reconstruction scanner's high-overhead
`pathlib` traversal with bounded `scandir` enumeration and direct reads.

On the same APFS host that produced the 42,964.957 ms scan, a deliberately cold
legacy sample reproduced at 41,896.687 ms. The accepted scanner's three 10,000
fact samples were 2,142.319–2,424.108 ms (2,271.987 ms median), and complete
candidate reconstruction measured 2,192.730 ms. In Docker/Linux, the same
canonical representation enumerated 10,000 facts in 134.357 ms median and
rebuilt the projection in 140.738 ms.

The historical lesson actually earned is:

> **One logical fact per immutable canonical object is part of PORTER's present
> audit and publication model. One expensive Python path ceremony per fact is
> not. O(N) truth is honest; an unstable filesystem constant is accidental.**

The resulting representation is better: identical truth, identity, replay,
inodes, ordinary mutation, Host causality and auditability; materially cheaper
and dramatically less variable disaster reconstruction.

## What took 42.965 seconds

The old path performed:

```text
Path.glob collections/by-package
  → create a set of Package names
Path.glob acceptances
  → sort Path objects
  → Path.read_text for every AC
  → JSON decode every AC
  → extract AC → Package
  → one set membership test for CL association
```

It did not open 10,000 CL facts. CL association was already O(1) set membership.
It opened and decoded every AC because Kind and exact Package identity live in
the canonical AC. The cold legacy reproduction took 41.897 s; two immediately
warm repetitions took 2.164 and 2.173 s. The 19× swing with identical N and
bytes proves that 43 seconds was not the cost of JSON or relationship logic.

The accepted measured scanner at 10,000 reported:

| Phase | Time | Share of 2,271.987 ms |
|---|---:|---:|
| directory enumeration + path discovery | 6.506 ms | 0.29% |
| file open | 2,059.319 ms | 90.64% |
| read 4,848,890 bytes | 94.893 ms | 4.18% |
| JSON decode | 48.869 ms | 2.15% |
| fact validation | 5.784 ms | 0.25% |
| AC/Package + CL relationship lookup | 3.796 ms | 0.17% |
| loop, close and measurement remainder | 52.820 ms | 2.32% |

Wall time was 2,271.987 ms, process CPU 424.062 ms, and wall-minus-CPU was
1,847.925 ms. That last value is a filesystem-wait estimate, not kernel tracing.
The scan visited two directories, opened 10,000 files, read 4,848,890 bytes,
decoded and validated 10,000 ACs, performed 10,000 AC/Package lookups and 10,000
CL membership checks. It acquired no locks and performs no explicit path `stat`.
The sandbox did not permit syscall tracing, so these are application-level
counters rather than invented kernel figures.

On Docker/Linux, open time was only 14.168 ms; reading was 57.637 ms, decoding
34.005 ms, and complete enumeration was 134.357 ms with 133.619 ms CPU. The
comparison establishes that N filesystem objects can be cheap on the intended
Linux substrate while also bounding the APFS-host pathology.

## Scaling curve

Ten percent of ACs were given canonical CL associations in these runs.

| Platform / representation | 100 | 1,000 | 10,000 |
|---|---:|---:|---:|
| APFS legacy median | 107.361 ms | 815.494 ms | 2,172.592 ms* |
| APFS accepted scanner median | 105.541 ms | 208.685 ms | 2,271.987 ms |
| APFS complete candidate rebuild | 101.380 ms | 213.112 ms | 2,192.730 ms |
| Docker/Linux legacy median | 3.274 ms | 13.830 ms | not rerun |
| Docker/Linux accepted scanner median | 1.990 ms | 13.509 ms | 134.357 ms |
| Docker/Linux complete candidate rebuild | 13.481 ms | 15.859 ms | 140.738 ms |

\* The warm median conceals a 41,896.687 ms legacy maximum. The accepted APFS
scanner range at 10,000 was 2,142.319–2,424.108 ms.

The Linux curve is the clean result: approximately linear with a small constant.
O(N) is fundamental while reconstruction must examine N independent facts.
The old constant and variance are not. 100,000 was not run: the 10,000 Linux
result already falsified the claim that independent files inherently cost tens
of seconds, while APFS creation of another 100,000-file fixture would measure
the host bridge more than PORTER.

## Representations put on trial

### A — independent files, legacy traversal

Retained as control and rejected as an enumeration implementation. It preserves
all semantics but exhibits pathological cold variance on APFS.

### B — disposable catalogue

Rejected before production implementation by the completeness falsification.
A catalogue entry can be validated against its named AC, so invented identities,
wrong digests and duplicates can be made harmless. A missing entry cannot be
detected without enumerating original ACs. Saying “complete through X” would
make X authority over the absence of later history—AC2 under another name.

Deleting, truncating, corrupting, staling, partially publishing, or substituting
an old catalogue must therefore force the same canonical scan. Such a catalogue
can accelerate a second scan but cannot safely accelerate the disaster scan
under trial. Maintaining it would add ordinary mutation cost and another failure
surface for no earned recovery benefit. No catalogue was added, so when the
only existing accelerator (`PORTER-CANDIDATES/1`) disappears or lies, original
AC and CL still reconstruct it exactly as before.

### C — bounded native directory enumeration

Accepted. `os.scandir` obtains names from exactly two known canonical families,
sorts AC names for deterministic traversal, directly opens and reads each AC,
validates the minimal shape reconstruction consumes, and checks Package identity
against the canonical CL association-name set. Unknown files cannot invent AC.
Malformed or truncated AC fails closed rather than manufacturing history.

This changes neither hierarchy nor Host IPC ABI. It removes redundant language-
level path machinery and bounds directory visits; it adds no durable state.

### D — packed immutable segments

Rejected for this generation. Logical identity could in principle survive a
framed record with per-record digest, but append alone cannot preserve the
current threshold:

```text
before atomic canonical publication → no AC
after                         → exactly one durable AC
```

A segment needs framing, per-record validation, an append durability rule and a
recoverable commit marker. Without a marker, bytes written before `fsync` may
survive a crash and blur “before threshold”; with a marker, the marker becomes
part of canonical publication. Partial-tail rules, neighbouring-fact isolation,
segment sealing, concurrent append, export and repair would all become new
canonical semantics. Linux's 134 ms result provides no performance evidence
strong enough to buy that PORTER 2.0 question. Logically independent facts may
share storage in principle, but this experiment did not earn the threshold that
would make one independently true there.

### E — immutable enumeration manifests

Rejected by the same absence test as the catalogue. A manifest truthfully says
which facts its author observed; it cannot say no unlisted AC exists. Missing,
stale and old-substituted manifests must fall back to canonical enumeration.
Turning absence into evidence requires new canonical completeness authority.

## Durability, crash and lies

No canonical write path changed, so the existing matrix remains literal:

| Crash point | Result after restart |
|---|---|
| before AC write/publication | `FACT DOES NOT EXIST` |
| during AC temporary write | `FACT DOES NOT EXIST`; unpublished temporary bytes are not AC |
| after AC bytes, before atomic publication | `FACT DOES NOT EXIST` |
| immediately after AC publication | `FACT EXISTS`; candidate reconstruction finds it |
| during candidate update | AC exists; disposable projection is invalidated/rebuilt |
| after AC, before candidate update | AC exists; startup scan reconstructs the row |
| during reconstruction/publication | old usable projection or no usable projection; canonical facts unchanged |
| after CL publication, before projections | CL exists and wins over stale candidate state |

There is no enumeration accelerator to delete or corrupt. The scanner encounters
truth directly. An invented AC filename outside the `PKG-*.json` acceptance
family is ignored. A selected canonical file whose JSON is truncated or whose
Package shape is malformed stops reconstruction. It cannot make false history
true. Existing atomic AC/CL publication and exact replay tests remain the
durability evidence; neither threshold moved.

## Identity, replay, custody and audit

An `AC-…` remains the value of the `acceptance` field in its immutable canonical
JSON, not a row or segment offset. Exact Package identity/digest replay still
opens the same Package-named AC and returns the same acceptance. CL remains its
own `CL-…` fact. Current custody is still derived from AC and CL; candidate
reconstruction is AC minus CL; no application state participates.

Every fact remains independently inspectable with ordinary filesystem and JSON
tools. Its exact bytes and digest can be reproduced, corruption localises to one
file, export needs no database engine, and the Stack Inspector requires no new
parser. Auditability did not regress.

At 10,000 AC and 1,000 CL associations the synthetic fixture held 4,848,890
canonical AC bytes, 10,000 canonical AC inodes and 1,000 association-projection
inodes. A real population with 1,000 Collections retains another 1,000 canonical
CL inodes: 11,000 canonical and 12,000 total AC/CL/association objects. The
accepted scanner changes zero bytes/fact,
inodes/fact and fsyncs/fact. Inode pressure therefore remains an honest cost of
the present representation; this experiment did not earn a semantic trade to
remove it. Peak benchmark RSS was about 35 MiB on APFS.

## Ordinary cost and attention

The AC/CL writers are unchanged. A fresh 500-AC component probe measured:

| Component | median | p95 | p99 |
|---|---:|---:|---:|
| canonical AC | 3.226 ms | 5.324 ms | 7.231 ms |
| inbox projection | 3.056 ms | 5.112 ms | 6.596 ms |
| candidate projection | 1.553 ms | 2.589 ms | 3.774 ms |
| complete deposit | 8.288 ms | 12.526 ms | 15.419 ms |

These absolute values are a noisier session than the prior durability record;
the relevant result is structural: enumeration code is absent from ordinary AC,
CL and warm attention paths, so it adds zero fsyncs, bytes or inodes per fact.

Indexed attention after the change measured:

| relevant / 10,000 | median | p95 |
|---:|---:|---:|
| 0 | 0.307 ms | 0.344 ms |
| 1 | 1.415 ms | 2.177 ms |
| 10 | 6.892 ms | 9.649 ms |
| 100 | 26.500 ms | 31.229 ms |
| 1,000 | 261.553 ms | 310.769 ms |

The protected 0.295/1.338 ms historical result is statistically unchanged.
Candidate rows remain hints and selected rows still validate against canonical
AC and CL.

## Security, causality and conformance

Admission is unchanged and still precedes AC. Refused correspondence cannot
reach this read-only reconstruction path or create canonical facts, candidate
rows, catalogues, segment garbage or manifests. The existing hostile tests for
unknown/spoofed identities, Kind, proof, size, expiry, custody budget and 10,000
attempt pressure remain green.

Enumeration is called only by Porter-local projection recovery. It has no signal,
watcher, callback, socket, Runtime or adapter reference. It cannot wake Host,
invoke an adapter, create a Round or cause application execution. Runtime,
applications, adapters, native carriage, concurrency, MailTube and Rent-a-Porter
were untouched.

The focused history/candidate suite passed 20 tests locally. Full local discovery
ran 91 tests: 89 passed and the two modules requiring the host's absent
`cryptography` package could not import. The complete Docker/Linux environment
ran all 106 tests successfully, including native carriage and rendezvous. No
conformance semantics changed.

Raw APFS, Linux and attention results are in:

- `benchmarks/results/canonical-history-enumeration.json`
- `benchmarks/results/canonical-history-enumeration-linux.json`
- `benchmarks/results/canonical-history-attention.json`

The reproducible profiler is `benchmarks/canonical_history_enumeration.py`.
