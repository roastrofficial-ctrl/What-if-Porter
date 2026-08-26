# PORTER-AUTHORITY/1 — portable authority and fork knowledge check

Measured 26 August 2026. Plural Standing showed that honest authority history is
independently replayable, while authorized equivocation makes local arrival
order choose incompatible current successors. This experiment tested the
smallest prerequisite needed to remove that order dependence without making
custodians coordinate or pretending a fork has a winner.

## Verdict

**The primary and secondary propositions survive. Asymmetric portable
transitions plus evidence-set interpretation let independent verifiers
reconstruct one honest lineage or the same explicit unresolved fork, regardless
of delivery order. A known fork can fail closed for new acceptance without
altering historical AC.**

The result does not prevent authority equivocation and does not recover from it.
It makes equivocation undeniable to anyone who later obtains both signed
branches. The correct epistemic distinction remains:

```text
one branch held:  no fork is known
two branches held: fork is known
```

Neither state proves that no hidden branch exists.

No custodian consensus, online authority, Host participation, global Standing
service, timestamp ordering or canonical Host-to-custodian map was required.

## Reproduction

```sh
./tests/docker_authority.sh
docker run --rm --network none --entrypoint python \
  -v "$(pwd):/src:ro" -w /src porter-attestation-check \
  -m benchmarks.authority
```

## Minimum trusted root

A fresh verifier receives one out-of-band `AUTHORITY_ROOT` assertion:

```text
authority identity and generation
Ed25519 public key
recipient
relationship sender
genesis Introduction and its public terms
```

The root says only that this public key may issue transitions for this exact
recipient relationship beginning at this exact genesis. It is not supplied by
or identified with a custodian. D/E/F may retain the same root after A/B/C and
all their operational keys and stores are destroyed.

“Out-of-band” is not magic. An operator or provisioning system must place this
exact trust anchor at the new custody boundary. Existing PORTER does not yet
define who may replace it. Root succession and recovery remain deliberately
unsolved pressures.

## Portable transition

Each `AUTHORITY_TRANSITION` is Ed25519-signed over:

| Field | Required binding |
|---|---|
| authority identity and generation | rejects unknown or obsolete authority context |
| root identity | prevents reuse beneath another bootstrap assertion |
| recipient | prevents Host/relationship transplantation |
| sender | prevents transplantation to another correspondent |
| predecessor | establishes the exact occupied continuity slot |
| successor | identifies the candidate current Introduction |
| successor terms | prevents restriction substitution or widening |
| ceremony identity | binds the transition to its issuance identity |
| transition identity | content-addresses replay and durable storage |

No timestamp is present because time cannot choose between two equally signed
successors. No custodian identity is present because authority history is not
topology. The verifier possesses only a public key and cannot forge another
transition.

Mutation of every security-relevant field, signature corruption, an unknown
signing key, a different authority generation, recipient/predecessor transplant,
retained-byte corruption and duplicate delivery were attacked. Substitution and
unknown authority failed; exact duplicate delivery was idempotent.

## Evidence-set interpretation

The durable store retains signed transitions by content identity. Current
knowledge is reconstructed from the complete verified set; no mutable “latest”
record is authoritative.

The interpreter begins at the trusted genesis and follows predecessor slots:

- zero reachable successor: current end of the known lineage;
- one successor: extend the lineage;
- more than one valid successor: `FORKED` at that predecessor;
- valid disconnected transitions: `PENDING` evidence;
- no trusted root: `UNKNOWN`.

Transition IDs, pending IDs and fork branches are sorted in the derived result.
Arrival order is absent from the semantics.

The chain `P0→P1→P2→P3` was delivered to D, E and F in three different orders,
with restarts between deliveries. All produced byte-equivalent `CURRENT(P3)`
knowledge. All six permutations of the same evidence set produced the same
result. Out-of-order evidence remained pending until its predecessor became
reachable.

## Hidden and revealed fork

D initially held:

```text
P0 → P1 → X
```

It legitimately derived `CURRENT(X)`. This means only “X is current in the valid
evidence I hold.” Unknown to D, the authority had also signed `P1→Y`.

When Y arrived, D reconstructed:

```text
FORKED(
  predecessor=P1,
  branches=[X,Y]
)
```

Y-then-X, X-then-Y, simultaneous input, restart between inputs, duplicate X,
and exported evidence delivered in reverse order all derived the identical
fork. The authority may deny intent, but cannot deny that its key signed both
exact statements without repudiating the trusted root itself.

The fork is portable evidence rather than D's opinion. An unrelated E imported
the raw signed transitions, used only the trusted public root, and independently
derived the same fork. E needed no D key, database, HMAC secret, sibling or
authority connection.

## Fail-closed admission knowledge

Before Y was known, D could authorize new correspondence naming X according to
its evidence. After Y became known, attempts under X, Y and predecessor P1 all
failed closed. There is no evidence-supported current branch.

An AC created under X before fork knowledge remained historical truth. Exact
replay returned historical acceptance rather than attempting a new authority
decision. Authority evidence therefore changes future authorization knowledge;
it does not rewrite custody history.

The fail-closed scope is one recipient/sender relationship. Unrelated Hosts and
relationships need not stop.

## Infrastructure replacement

An honest `P0→P1→P2` evidence set and a forked `P0→P1→{X,Y}` set were each
exported. Every old store was destroyed. Fresh roots imported the transitions in
reverse order and reconstructed respectively:

```text
before: CURRENT(P2)  after: CURRENT(P2)
before: FORKED(X,Y)  after: FORKED(X,Y)
```

Infrastructure replacement preserves the epistemic result exactly. It neither
erases contradiction nor makes a Porter authoritative for the Host.

## The deliberate integration boundary

This laboratory does not replace production Standing or ceremony.

The portable transition can safely publish the successor Introduction identity
and public restrictions. Existing Standing admission, however, uses a symmetric
operational secret. Publishing that secret in portable history would give every
outside verifier correspondence-forging capability—the same category error this
experiment removed from ceremony verification.

Consequently `PORTER-AUTHORITY/1` currently proves which Introduction is current
or forked; it does not provision private admission capability or directly create
production AC. Integration requires a separate earned answer: confidential
per-recipient credential delivery, or asymmetric correspondence authorization.
That pressure is recorded rather than solved here.

## What each participant can establish

### Ceremonial authority

It knows and signs the exact transition. It can sign competing successors. Once
both signatures are disclosed, it cannot cryptographically deny equivocation.
Its signature proves speech, not honesty, uniqueness, propagation or storage.

### Individual custodian

From its root and held evidence it can independently derive `UNKNOWN`,
`PENDING`, `CURRENT` or `FORKED`. It cannot detect an undisclosed branch or claim
that its evidence set is globally complete. A known reachable fork is sufficient
to refuse new local AC creation for that relationship.

### New custodian

It trusts the scoped root assertion—not an old custodian—and verifies raw
history itself. It needs no old operational identity or database. It still needs
separate provisioning of any private material used by production admission.

### Recipient Host

The networkless Host does not participate. Authority remains infrastructure
policy, not Host intent. Nothing here authorizes a Porter to speak as the Host.

### Outside verifier

Given root plus transitions, it verifies signer identity, exact transition,
continuity and any disclosed fork. It cannot establish absence of hidden forks,
global propagation, present custodian enforcement, or a canonical winner after
equivocation.

## Real-World Pressure Ledger

### Security

Ed25519 removes verifier-forging capability and makes disclosed equivocation
portable. Authority-key compromise permits arbitrary valid transitions and
forks until a separate recovery mechanism intervenes. Detection makes damage
auditable and enables local fail-closed behavior; it does not undo compromise.

### Availability

Honest history needs neither an online signer nor custodian coordination after
issuance. Pending history does not disable the last unambiguous current lineage.
A known reachable fork disables new AC only for the affected relationship.
Historical custody and unrelated correspondence continue.

### Trust

The minimum long-lived anchor is a scoped authority public key, generation,
recipient/sender pair and genesis Standing. It survives Porter replacement.
Who may rotate or recover this anchor is intentionally unanswered; allowing the
equivocating key alone to select a winner would not be recovery.

### Privacy

Portable evidence exposes recipient, sender, authority, Introduction topology,
ceremony IDs, and successor restrictions to every holder. Exportable fork proof
therefore exports relationship metadata. Private operational credentials must
not appear in this evidence.

### Operations

Operators may report local states and exchange signed evidence without becoming
authority. `PENDING` means missing continuity, `FORKED` means contradictory
signed successors, `UNKNOWN` means no trusted root, and `CURRENT` remains
qualified by the evidence held. Monitoring cannot safely claim global absence
of a hidden branch.

### Performance

Measured locally in the offline Docker image:

| Operation | Median |
|---|---:|
| sign one transition | 0.048 ms |
| verify and detect two-branch fork | 0.157 ms |
| derive chain length 1 | 0.083 ms |
| derive chain length 10 | 0.830 ms |
| derive chain length 100 | 7.783 ms |
| derive chain length 1,000 | 77.419 ms |

Encoded storage grew from 498 bytes for one transition to 501,567 bytes for
1,000: approximately 500 bytes per transition. Verification/reconstruction is
linear in evidence count. These are laboratory medians, not capacity promises.

### Migration

Honest and forked evidence survived complete store/identity replacement with
identical derived knowledge. The authority root, not any Porter identity, is the
continuity anchor.

### Evidence

Portable claims now include signer identity, exact scoped transition,
restrictions, continuity and disclosed equivocation. Local claims remain receipt
of evidence, current local enforcement, AC/CL, physical custody and propagation.
No evidence proves there is no hidden fork.

## Stop condition

The experiment stops successfully before recovery.

`PORTER-AUTHORITY/1` demonstrates that detectable equivocation is sufficient for
PORTER to remain honest about the authority evidence it knows. It replaces
arrival-order branch choice with deterministic unresolved fork knowledge and
fail-closed future authorization.

It does not make the signer non-equivocating, choose a winner, rotate a
compromised root, provision operational secrets or integrate plural ceremony
into production. Those are distinct future pressures and have not been earned
as one mechanism merely because this experiment exposed them.
