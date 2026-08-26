# PORTER-THRESHOLD/1 — Replication and correspondence check

Measured 24 August 2026. The first check established that M distinct signed
claims can corroborate historical acceptance under `f < M`. This check asks
whether THRESHOLD gives a networkless Host a property unavailable from ordinary
replication with the same signatures and fault model.

## Verdict

**It does not. THRESHOLD is replication with signed witnesses.**

The control replicated one exact immutable PORTER Package into three independent
Porter stores. Each store published its own AC and signed its own acceptance
claim. The same 2-of-3 reconciliation accepted two distinct witnesses, rejected
one, rejected forgery and duplicate voting, retained equivocation, survived one
custodian's loss, and failed after total custody loss. Its fault boundary was
identical to the Logical Deposit prototype.

No Porter-native consensus, custody transition or Host threshold emerged.
`M` is a sender-side evidence policy over replicated AC claims. The useful
properties are replication availability and independently verifiable receipts;
combining them deserves configuration and tooling, not a new correspondence
abstraction.

This is the requested stopping result. The experiment does not promote
THRESHOLD into the daemon or protocol lifecycle.

## Reproduction

```sh
./tests/docker_threshold.sh
```

The second check adds eight hostile lifecycle cases to the first check's six.
All operate inside Docker `--network none`.

## The unnecessary premise

The first prototype accepted this premise from the proposal:

> independent custody requires independent `PKG-*` identities

PORTER does not require that. Package identity names correspondence, while an
AC is already recipient-Porter-local and a native `CU-*` names one physical
carriage unit. Three stores accepted the same `PKG-*` and Package digest while
publishing three distinct `AC-*` identities:

```text
one immutable PKG / one digest
  ├─ carriage unit → Porter A → AC-A
  ├─ carriage unit → Porter B → AC-B
  └─ carriage unit → Porter C → AC-C
```

The Porters need not share a filesystem, AC namespace or endpoint. Replication
location belongs in sender-side carriage bookkeeping. It need not alter the
correspondence envelope.

The Logical Deposit was therefore a repair for generating unnecessary new
Package identities. Once exact Package replication is allowed, its identity,
digest, member-to-Package map and payload wrapper disappear. A compact local
replication record needs only the pinned plan, Package identity/digest, members
and required witness count.

## What each participant can prove

| Threshold | Sender Host | Individual Porter | Recipient Host | Outside verifier |
|---|---|---|---|---|
| LG | it durably lodged exact PKG | nothing | nothing | local fact only unless exported/authenticated |
| AC | nothing until evidence returns | its store accepted responsibility at that time | nothing until attention | ordinary unsigned receipt is not independent proof |
| signed witness | member signed exact PKG digest and AC claim | what it asserted | later verifies the assertion | verifies signer and bytes, not current storage truth |
| 2-of-3 confirmation | two distinct members signed | only its own claim | learns it on a later Round | under `f < 2`, at least one signer was honest at claim time |
| one CL/recovery | exact PKG crossed from named Porter into Host custody | its responsibility ended for that copy | exact correspondence is recoverable locally | verifies exported CL/history, not application processing |
| later failed recovery | attempt did not recover | may know local cause | cannot distinguish loss, withholding, partition or stale route | no current-custody conclusion beyond the failed observation |

A confirmation is historical. It is not a lease, read quorum, proof of current
custody, or promise that M members remain reachable. Fresh nonce-bound
possession proofs could provide a later observation, but those are replicated
storage audits and still cannot guarantee future retrieval.

## Hostile lifecycle results

### Roster replacement

The local replication record pins the exact signed Roster/plan identity. A new
Roster cannot reinterpret old claims or change which Package they concern.
Outstanding work remains governed by its original plan. Re-replication under a
new plan may copy the same exact Package; it does not create new correspondence.

### Standing succession exposes a missing prerequisite

The draft says a Roster is signed by a “recipient Standing key.” Current PORTER
Standing is not such a general signing authority. It is recipient-local,
sender-specific admission history (`IN → SC → IN`) with one predecessor slot.
No recipient Roster-signing root or succession chain presently exists.

The experiment created an old authority's late Roster and a successor
authority's earlier Roster. Both signatures verify independently. `RS` contains
no authority generation, predecessor or unique transition slot, so a verifier
cannot prove which authority was current when the late Roster purportedly took
effect. An `effective_from` chosen by the signer does not order hostile facts.

This affects replication and THRESHOLD equally. Deployable signed replication
plans require a separately earned authority-succession mechanism or explicit
reuse of a suitable existing continuity chain; calling it Standing-governed
does not provide one.

### Custody loss and recovery

After two signed acceptances, destroying both stores leaves a perfectly valid
confirmation and no retrievable correspondence. That is not contradictory: the
claims remain historical facts.

With one store surviving, one exact Package retrieval is sufficient. Requiring
M Collections buys no integrity once the recovered identity and digest match;
it only copies the same correspondence into Host custody repeatedly. Other
replicas may be released, expired or retained according to replication policy.

### Equivocation

A member can sign a different digest for the pinned Package identity. The
control retains the signed conflict and refuses confirmation, exactly as the
THRESHOLD prototype did. This is evidence of replica equivocation, not
Byzantine consensus: no value is selected, no global order is established, and
honest members do not agree with one another through the protocol.

### Networkless Host

The Host gains no new active capability. Porters accept replicas while it is
absent. On a Host-chosen Round it may inspect corroboration and collect from one
available custodian. Compared with single custody it gains failure-domain
redundancy and audit evidence. Compared with ordinary signed replication it
gains nothing distinct.

## Does Logical Deposit escape?

**Not in the pressures tested. Package remains correspondence; Package copies
and Carriage Units are its physical manifestations.**

Three independent pressures already preserve Package identity:

- **Rendezvous movement:** PORTER 1.5 retains the unchanged outgoing Package
  while route knowledge and operational keys change. Existing native tests
  recover a Package lodged before movement without minting another identity.
- **Standing succession:** exact identity-and-digest replay recovers the
  historical AC after capability rotation or termination. A new logical layer
  would add no continuity.
- **Custodian recovery:** this check stored the same exact Package under two
  independent ACs and recovered it through either store. The recovery fact
  binds the original Package digest.

Returns also already name correspondence through `in_reply_to`; choosing a
different replica plan for a Return changes its custody path, not the identity
of the originating Package. Continuous Correspondence may eventually require a
conversation, flow or operation identity spanning several genuinely different
Packages, but that would be an application/protocol sequencing pressure—not a
physical-manifestation identity. No such abstraction is earned here.

A future experiment should reconsider a higher identity only if it independently
requires one semantic operation to have non-identical encodings, chunk sets,
redactions or transformations that cannot share an exact Package. Replication,
rendezvous, succession and recovery do not.

## What survives the THRESHOLD work

- independently signed Porter custody receipts are useful beyond replication;
- an exact signed replication plan must be pinned for historical verification;
- distinct signer counting and retained equivocation are necessary audit rules;
- 2-of-3 is a coherent availability/audit policy under at most one dishonest or
  unavailable operator;
- one verified recovery, not M Collections, is the Host custody threshold;
- current possession requires a fresh audit and remains different from
  historical acceptance.

These belong to a future **signed replication** experiment. `TD`, logical
payload wrappers, N Package identities, `TC` as a new canonical custody fact and
`TR` as threshold Collection do not survive this check.

## Implementation boundary

`porter.replication` is a disposable control model, not a proposed production
module. It records replication of one Package, signs per-replica custody claims,
applies the same M-witness policy, and records one exact recovery. It exists to
falsify a distinct THRESHOLD abstraction. The daemon, LG/AC/CL thresholds,
Package envelope, Host Runtime and native carriage remain unchanged.
