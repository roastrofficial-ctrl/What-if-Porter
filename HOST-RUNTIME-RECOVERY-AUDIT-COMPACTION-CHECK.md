# PORTER Recovery Audit Compaction Check

Status: experiment complete; optimization rejected, 2026-08-21.

This final experiment asks whether the earned O(N) warm recovery audit can be
replaced by a constant-size root or hierarchical disposable fingerprint which
expands only mismatching branches.

It cannot—not under the current flat canonical layout and corruption model.
Compaction would either miss ordinary leaf damage, introduce a newly trusted
mutation channel, or re-read every leaf and recover the same O(N) cost.

## Tempting result

At 1,000 canonical Collections:

| Audit | Time | Verdict after in-place association corruption |
|---|---:|---|
| Earned leaf audit | 394.719 ms | Full reconstruction and repair |
| Root directory fingerprint | 0.026 ms median | Incorrectly clean |

The root shortcut is roughly 15,100x faster. It is also unsound.

Changing the contents of an existing Package-to-CL association changes the
leaf's metadata and bytes but not the parent directory's inode, entry count, or
mtime. The prototype root fingerprint remained exactly equal. The current
frontier audit inspected the required leaf signature and association identity,
invalidated the frontier, parsed canonical history, and restored the correct CL.

Raw evidence is in
`benchmarks/results/recovery-audit-compaction.json`.

## Why a hierarchy does not fix authority

A disposable tree can store a digest for each branch and a root over those
digests. On startup, however, comparing the stored root with itself proves only
that the disposable tree was not changed. It does not prove that canonical CL
or projection leaves still match it.

There are only three ways to obtain a current branch digest:

1. Read and hash/stat every leaf in the branch. Across unchanged branches this
   is still O(N), equivalent to the earned audit.
2. Trust every mutation to update the branch digest. That makes the mutation
   channel authoritative enough to conceal unreported deletion, corruption, or
   crash gaps—the exact authority a disposable frontier must not possess.
3. Trust filesystem directory metadata as the mutation oracle. Existing-file
   content changes do not necessarily change parent directory metadata, as the
   conformance vector demonstrates.

More levels improve localisation only after a trustworthy mismatch is known.
They do not create the missing proof that an apparently unchanged branch still
matches its leaves.

## Alternatives rejected

### Publication-maintained dirty markers

Writing a dirty marker before CL publication can safely identify interruptions
inside code paths which obey the marker protocol. It cannot detect external or
partial projection damage which bypasses that path. Making the marker decisive
would narrow the recovery model from auditing current evidence to trusting all
writers.

### Sharding canonical and projection directories

Physical prefix directories could reduce the number of leaves examined after
an entry add/delete because a shard directory mtime would change. It would alter
the established storage layout and still miss in-place changes to existing
leaves unless every leaf is inspected or all writers are trusted.

### Filesystem journals or watchers

OS change journals may provide efficient operational hints but are not portable,
may lose history across restart or rotation, and cannot become PORTER truth.
Their absence would require the same full audit, while their presence still
inherits platform-specific integrity assumptions.

### Periodic or probabilistic leaf sampling

Sampling reduces expected detection latency, not correctness risk. A startup
could declare recovery complete while the one required projection it did not
sample was missing or corrupt. That is not the contract under experiment.

## What remains earned

The current frontier has the correct shape:

- clean history parses zero canonical JSON facts;
- exact extensions parse only new facts;
- every old canonical and required projection leaf is audited;
- any inconsistency returns to full canonical reconstruction;
- the frontier remains disposable and removable;
- 10,000-history warm startup is 3.2 seconds rather than 128.5 seconds cold.

Its remaining O(N) cost is not accidental inefficiency. It is the cost of
retaining the present authority boundary without a stronger storage-integrity
primitive.

## Verdict

Recovery audit compaction does **not** earn itself. No production recovery path
was weakened or replaced. The unsafe prototype remains benchmark evidence only;
the conformance vector permanently records why directory-level shortcuts are
insufficient.

The optimization boundary is now explicit:

> A disposable recovery summary may save interpretation and repair work. It may
> not save the observation required to prove that canonical and required
> projection leaves still agree.

Further work in this area should wait for a materially different storage
integrity model or real startup pressure beyond the present 10,000-history
measurements. There is no automatically earned follow-up experiment.
