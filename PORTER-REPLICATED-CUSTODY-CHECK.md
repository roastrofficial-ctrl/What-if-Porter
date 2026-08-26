# PORTER replicated custody — ontology check

Measured 24 August 2026. THRESHOLD remains rejected: M-of-N is an evidence
policy over replicated custody, not a correspondence primitive. This experiment
asks whether one immutable Package can be under several independent Porter
responsibilities without a global replica lifecycle.

## Verdict

**The falsification target survived. PORTER custody is relationship-local.**

Multiple Porters may independently accept and collect the same immutable
correspondence. Each `AC` means its issuing Porter assumed responsibility for
its own custody relationship. Each `CL` means that Porter's accepted copy
crossed into recoverable Host custody. Neither fact claims exclusivity, global
availability, unique recovery or application processing.

Exact replication requires no change to Package, AC or CL and earns no
replication-specific lifecycle fact. Sender-side policy may choose several
custodians and count evidence, but no Porter needs sibling awareness.

One caveat is general rather than replication-specific: accepted correspondence
cannot currently be voluntarily discarded. Package expiry gates admission; it
does not terminate an already-crossed AC. Silent post-AC disposal is custody
loss or breach. A future release/abandonment experiment would apply equally to
one Porter and was not invented here.

## Reproduction

```sh
./tests/docker_replicated_custody.sh
```

Nine hostile lifecycle cases run in Docker `--network none` against the existing
AC/CL implementation. The daemon and custody lifecycle are unchanged.

## Independent Acceptance

Three independent stores accepted the exact same Package identity and digest.
They produced three distinct AC identities and each truthfully reported local
`RECIPIENT_PORTER` custody.

Responsibility is therefore neither exclusive nor correspondence-wide. It is
**custodian-local responsibility for one exact correspondence**:

```text
PKG-X / digest D
  ├─ AC-A: A is responsible here
  ├─ AC-B: B is responsible here
  └─ AC-C: C is responsible here
```

No AC says that another custodian does or does not exist. This was already
implicit in the fact's local canonical store; replication makes the locality
visible.

## Partial and redundant Collection

After A collected:

- the Host had recovered `PKG-X` through A, not a new correspondence called
  “A's copy”;
- A's local custody relationship reported `RECIPIENT_HOST` and its
  responsibility ended through `CL-A`;
- B and C continued to report `RECIPIENT_PORTER` under `AC-B` and `AC-C`;
- neither B nor C needed to learn about `CL-A`.

B could later publish `CL-B`. `CL-A` and `CL-B` had distinct identities and
bound distinct ACs, but contained the exact same Package. The second transfer
was redundant recovery of existing correspondence, not duplicate
correspondence. It does not authorize a second application effect.

This is expressible as the union of local histories:

```text
A: PKG-X → AC-A → CL-A
B: PKG-X → AC-B → CL-B
C: PKG-X → AC-C
```

There is no honest global `RECOVERED` or `COMPLETE` fact. A knows its CL; B and C
do not. The Host may know several histories only after a Host-chosen inspection.

## Crash and redundant recovery

Before A's CL threshold, an interrupted association reservation invented no
Collection. The Host recovered the exact Package from B, and A remained
responsible. A later CL was redundant but coherent.

After A's CL threshold, A's ordinary Collection recovery reconstructed Host
custody without consulting B. B remained independently responsible. The
existing local crash boundary therefore survives unchanged.

Package identity is sufficient to recognize both recoveries as the same
correspondence. It does not provide exactly-once application execution, and
PORTER never claimed that. Replication tooling or the application must avoid or
tolerate redispatch after seeing the same `PKG-*`; no global custody transition
can decide whether an external application effect occurred before a crash.

## Replica disappearance

Destroying one store erased that custodian's present local knowledge and bytes.
Other stores and their responsibilities were unchanged. A separately retained
AC or signed statement remained evidence that the lost Porter accepted at the
stated time; it did not prove why the store disappeared or that bytes remained.

The cases reduce cleanly:

- loss before any CL: that copy becomes unavailable; surviving AC custodians
  can still transfer theirs;
- loss after another replica's CL: Host recovery remains true and the lost
  custodian's later state is unknown;
- all but one lost: the survivor remains responsible and sufficient for one
  recovery;
- all lost after a CL: the historical CL remains true; recoverable Host custody
  depends on the Host store that CL established, not surviving Porter replicas.

Historical AC/CL facts must not be mutated to narrate current storage loss.

## Late Acceptance

B legitimately accepted the exact Package after A had already published CL.
B had no global channel through which to know A's state, and none was needed:
it assumed responsibility for bytes offered into its own custody relationship.

Rejecting this AC would require a globally observable “already recovered” fact,
which no Porter can know while the Host remains networkless and Host attention
remains pull-based. The successful late AC is strong evidence that
responsibility is local rather than secret global correspondence state.

The sender may decide that late replication is no longer useful and stop its
carriage attempt. That is sender-side policy, not recipient Porter truth.

## Expiry and release

An accepted Package remained collectible after its envelope expiry. This is
correct under current PORTER semantics: expiry prevents a new AC after the
deadline; it is not a retention lease and does not undo an existing AC.

A Porter therefore may not silently “expire its replica” after AC. Removing the
bytes leaves the historical acceptance intact but makes the responsibility
unfulfillable. PORTER lacks a voluntary release-without-transfer fact, but the
single-Porter control gives the same result. Replication did not earn such a
fact, and this check does not add one merely to complete a diagram.

## Independently signed custody evidence

This result survives replication and is useful with exactly one Porter.

The experimental `SIGNED_ACCEPTANCE` statement binds:

- evidence vocabulary and assertion kind;
- Porter and recipient identity;
- Package identity and canonical digest;
- AC identity and acceptance time;
- the exact durable-acceptance state;
- a content-derived statement identity and Ed25519 signature.

The issuer reads the canonical `acceptances/PKG-….json` before signing. With no
AC, signing refuses. Because AC publication is the existing atomic durability
threshold, the normal issuer cannot publish testimony before the fact it names.
Substitution of Porter, Package or digest fails expected-context verification.

This distinguishes:

```text
local software says “A accepted”
```

from:

```text
the holder of A's trusted evidence key signed “I published this exact AC”
```

It remains authenticated testimony. A dishonest or compromised signer can lie,
and a valid old statement remains verifiable after the bytes are destroyed. It
does not prove present possession.

The minimum deployment mechanism also needs trusted provenance and succession
for each Porter's evidence key. Current X25519 carriage keys are not signing
keys, and an ungoverned configured Ed25519 key would reproduce the Roster-key
continuity gap. That key lifecycle has not been earned here, so signed evidence
remains an experimental general PORTER evidence capability rather than daemon
output.

## Participant knowledge at each threshold

| Event | Issuing Porter | Sender/depositor | Networkless Host | Later outside verifier |
|---|---|---|---|---|
| LG | knows nothing unless carriage arrives | proves local exact lodgement | knows nothing | exported LG is only as trustworthy as its provenance |
| local AC | knows it assumed responsibility here | may learn ordinary receipt later | learns only on chosen attention | cannot attribute unsigned JSON independently |
| signed AC | knows what its key asserted | verifies named Porter's testimony | may verify during a Round | verifies attribution and bound history with a trusted key |
| A's CL | knows A transferred its copy | generally does not learn it | proves exact PKG recoverable through A | exported history proves transfer, not processing |
| B's surviving AC | B remains responsible | may retain old evidence only | may discover B on later attention | no statement about A, C or global availability |
| failed later attempt | knows only its local failure | knows its attempted observation | knows only if it made the attempt | cannot distinguish loss, withholding, partition or stale route |

At no point can a participant honestly infer replica count, global availability,
global recovery completeness or application outcome from one local history.

## Falsified ideas to discard

- global `REPLICATED`, `AVAILABLE`, `RECOVERED` or `COMPLETE` custody states;
- a replica count inside Package or AC;
- sibling awareness at recipient Porters;
- leader or elected replica responsibility;
- quorum Collection;
- a new Package or Logical Deposit identity per physical copy;
- treating envelope expiry as post-AC responsibility release;
- treating a signed AC as present-possession proof;
- solving duplicate application effects inside PORTER.

## Earned result

Exact replication is orthogonal to PORTER custody semantics. `PKG / CU / AC /
CL` remain coherent because AC and CL were already local facts about one
custodian's responsibility. Replication needs only external carriage/storage
policy.

Optional independently verifiable AC testimony is genuinely useful outside
replication. Its evidence-key identity and succession are the next unresolved
general problem; replication itself is complete.
