# PORTER Canonical Recovery Frontier under Large History

Status: experiment complete, 2026-08-21.

This experiment asks whether Porter and Host Runtime startup must parse and
rematerialize every historical canonical Collection, even when the immutable CL
set and every required projection remain unchanged.

The answer is no—but only after an audit. The frontier is disposable evidence of
previously checked work, never a source of custody truth. Missing, malformed,
contradictory, or incomplete evidence forces reconstruction from canonical CL
facts.

## Authority boundary

Canonical `collections/facts/CL-*.json` files remain the sole Collection
authority. The recovery frontier cannot:

- create or delete a CL;
- establish custody;
- change Package, Kind, collector, or application meaning;
- suppress a canonical fact not represented in the frontier;
- repair without consulting canonical truth when its audit fails; or
- survive as trusted state merely because it is well-formed JSON.

Deleting the frontier changes no PORTER truth. It causes a slower complete
reconstruction on the next startup.

## Frontier contents

`collections/recovery/frontier.json` records, for each previously recovered CL:

- canonical fact filename and immutable size/mtime signature;
- Package, Collection, collector, and opaque Package Kind needed for startup
  candidate discovery;
- required collected-Package projection signature; and
- required Package-to-CL association signature and expected CL identity.

The file is atomically replaced only after required projections exist. It is
locked as one local recovery operation, preventing competing Porter/Runtime
processes from replacing a newer exact extension with an older view.

The frontier deliberately contains no returned-control, application success,
worker, running, lease, queue, retry, or disposition state.

## Three startup modes

### Full reconstruction

Used when the frontier is absent, malformed, has an unknown schema, refers to a
missing old canonical fact, observes changed canonical metadata, or finds a
missing/changed required projection. Every current CL is parsed and
`materialize()` reconstructs projections under the existing Package lock. A new
frontier is written only after completion.

If canonical JSON itself is malformed, startup fails rather than blessing a
frontier or silently skipping the fact.

### Warm audit

When the frontier's fact set exactly matches the canonical directory, startup
audits every immutable fact signature and required projection signature plus the
association's CL identity. It parses zero CL JSON facts and performs no
materialization writes.

This remains O(N) metadata/projection auditing. It is intentionally not a
constant-time trust shortcut. The optimization removes historical JSON parsing,
locking, and repair work while retaining positive evidence that the cached
frontier still describes the directory.

### Exact extension

When every old entry audits successfully and the canonical directory contains
only additional fact filenames, startup parses and materializes exactly those
new facts. The old facts remain audited but are not reparsed. Any deletion or
mutation among old entries makes the extension suspect and selects full
reconstruction instead.

Because CL filenames are UUID-like rather than chronological, this is a set
extension, not a lexical cursor. Calling it a frontier describes verified
recovery progress, not ordering canonical history never promised.

## Duplicate startup scan removed

Previously the Runtime first parsed every CL during `recover_collections()` and
then `candidates()` parsed the directory again to locate collected Packages
lacking returned-control evidence.

The audited frontier now supplies only the minimal Package identity, Kind,
collector, and CL identity needed for recovery candidate selection. If one is
selected, the existing direct association loads its canonical CL before offer.
Thus warm startup does not immediately erase its gain with a second history
parse, and the CL-before-offer crash remains re-offerable.

Porter startup and Host Runtime startup use the same locked frontier. Whichever
starts first performs the required audit or reconstruction; the next process
normally receives a warm audit.

## Pressure results

The benchmark creates complete canonical facts and required projections. Cold
filesystem effects are intentionally retained in the no-frontier cell.

| History | Shape | Startup | CPU | Parsed CLs |
|---:|---|---:|---:|---:|
| 1,000 | No frontier | 11.304 s | 2.434 s | 1,000 |
| 1,000 | Warm audit | 387 ms | 98 ms | 0 |
| 1,001 | One exact addition | 263 ms | 71 ms | 1 |
| 1,001 | Missing projection | 1.477 s | 478 ms | 1,001 |
| 10,000 | No frontier | 128.485 s | 25.302 s | 10,000 |
| 10,000 | Warm audit | 3.221 s | 806 ms | 0 |
| 10,001 | One exact addition | 2.653 s | 729 ms | 1 |
| 10,001 | Missing projection | 13.111 s | 4.656 s | 10,001 |

Warm audit is 29.2x faster at 1,000 and 39.9x faster at 10,000 than the cold
no-frontier reconstruction. An exact one-fact extension parses exactly one
canonical JSON fact. The forced-full cells are faster than cold because the
directory and lock inodes are already warm in the filesystem cache; they remain
the relevant correctness result: one missing projection invalidates the entire
shortcut and reparses all history.

Warm audit at 10,000 still costs 3.2 seconds. That is the price of checking
10,000 fact and projection signatures rather than assuming a checkpoint is
true. This experiment does not claim constant-time startup.

Raw results are in `benchmarks/results/recovery-frontier.json`.

## Failure matrix

Conformance establishes:

- clean warm audit parses zero canonical facts;
- adding two CLs parses exactly two;
- deleting a collected projection forces full reconstruction and repairs it;
- changing an association forces full reconstruction and restores its CL;
- changing canonical fact bytes/metadata forces full reconstruction;
- deleting an old canonical fact invalidates the frontier;
- malformed or missing frontier forces full reconstruction;
- competing recovery calls serialize, yielding one reconstruction/extension and
  one warm audit rather than racing checkpoint writers;
- CL without returned-control evidence remains discoverable and re-offerable;
- frontier loss or process crash changes no canonical custody fact.

A crash while writing the frontier leaves either the previous complete atomic
file or no usable file. An old complete frontier may still admit an exact
extension; a partial/malformed replacement triggers full reconstruction.

## Limitations

The audit is designed for filesystem failure, interruption, and ordinary
corruption—not an attacker able to rewrite files while preserving their size,
timestamps, and surrounding local filesystem observations. PORTER's existing
local canonical store does not claim protection against a fully compromised
Host filesystem. Stronger cryptographic storage integrity would be a separate
security model, not something a disposable recovery projection can manufacture.

Canonical fact deletion is treated as frontier invalidation and reconstructed
from the facts which actually remain. Recovery does not use the disposable old
entry to recreate deleted canonical truth.

## Verdict

The recovery frontier earns itself. It removes repeated parsing and
materialization from the common clean startup, handles exact history extension
incrementally, eliminates the Runtime's duplicate recovery scan, and remains
aggressively disposable whenever its proof is incomplete.

The architectural rule is:

> Recovery progress may be remembered only when current canonical and
> projection evidence can audit that memory. Uncertainty returns to truth.

The one next experiment is **Recovery Audit Compaction**: determine whether the
O(N) warm audit can be reduced with hierarchical, disposable directory
fingerprints whose mismatching branch alone is expanded, while any missing root
or mismatched leaf still falls back to canonical verification and repair.
