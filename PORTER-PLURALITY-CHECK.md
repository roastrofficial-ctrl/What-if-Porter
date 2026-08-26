# PORTER plurality — bounded custodian check

Measured 24 August 2026. This experiment asks whether a Porter can be demoted
from the Host's singular network representative into one replaceable,
independently auditable custodian among several.

## Verdict

**The custody paradigm shift is supported, but native carriage still contains
one singular-identity seam.**

A networkless Host recovered one unchanged Package after its original custodian
was completely removed, while another late custodian independently retained the
same correspondence. No custodian coordinated with, elected, monitored or even
knew the identity of a sibling. Historical evidence remained attributable
across evidence-key rotation.

This establishes a coherent bounded role:

> A Porter speaks for its own custody relationship, never for the Host.

It does not yet establish a complete plurality substrate. Current PORTER
collapses Package recipient, Porter daemon identity, native-carriage recipient,
rendezvous identity and Standing recipient into one string. Several stores can
accept as the same recipient, but native rendezvous selects only one endpoint
and carriage key for that identity. The laboratory used independent direct
deposits to pressure custody, not a production fan-out transport.

The next earned architectural seam is therefore **recipient identity versus
custodian/carriage identity**, kept outside the immutable Package. It is not a
reason to add replication policy, Porter identity or a Roster to the Package.

## Reproduction

```sh
./tests/docker_porter_plurality.sh
```

Seven evidence-identity cases and five plurality cases run inside Docker
`--network none`. The existing daemon and PKG/LG/AC/CL lifecycle are unchanged.

## Evidence identity without Host impersonation

The experiment establishes a Porter-specific evidence-key chain beneath a
separately trusted continuity authority:

```text
Porter A continuity root
  → EK-A/0 valid [t0,t1)
  → EK-A/1 valid [t1,t2)
```

Each immutable `EK` binds Porter identity, generation, predecessor, operational
Ed25519 evidence key and a non-overlapping validity interval. The authority
signature does not make the Porter a Host authority. It authorizes only
attribution of that Porter's evidence statements.

The experiment showed:

- statements issued under EK/0 remain verifiable after EK/1 activates;
- a compromised EK/0 cannot produce testimony dated inside EK/1's interval;
- a forged authority signature fails;
- gaps and authority overlaps fail closed;
- two successors for one predecessor expose authority equivocation and suspend
  construction of a canonical history;
- a statement cannot claim an issuance time before the canonical AC it names.

As with rendezvous continuity, equivocation is detectable only by a verifier
that obtains both forks. The chain is not a transparency log and Porters do not
cross-monitor it. Compromise of the continuity root remains the local disaster
boundary for that custodian; it does not compromise a sibling's evidence key or
the Host's identity.

## The identity seam exposed

Today `Porter.deposit` enforces:

```text
Package.to == Porter.identity
```

and AC records that same value as `recipient`. This is adequate while “the
recipient” and “its one Porter” are treated as synonymous. It cannot by itself
attribute two independently operated custodians both carrying for `harmonicdb`.

The experimental signed statement preserves `recipient: harmonicdb` and adds
`custodian: porter-a` from the custodian's evidence identity. Two stores can
therefore produce independently verifiable statements about the same Host and
Package without changing either:

```text
PKG-X { to: harmonicdb }
  → AC at recipient service identity harmonicdb
  → signed by custodian porter-a / EK-A

PKG-X { to: harmonicdb }
  → another local AC at harmonicdb
  → signed by custodian porter-b / EK-B
```

This is sufficient for evidence attribution and custody replacement. It is not
yet sufficient for native fan-out because native route/key knowledge is indexed
by the single `to` identity. A future carriage experiment should test a local
mapping from one recipient to several independently identified carriage
destinations. That mapping belongs to depositor policy and CU framing, not the
Package envelope or correspondence semantics.

## Complete original-custodian removal

Porter A and Porter B independently accepted PKG-X and issued attributable
statements. A's entire store then disappeared. Porter C, whose continuity root
was already trusted by the experiment operator, accepted the exact same Package
later. The Host collected through B. C remained independently responsible.

Throughout:

- Package identity, digest, recipient and Kind never changed;
- no successor Porter inherited A's AC or claimed to be A;
- A's old signed statement remained historical testimony;
- B did not know A was gone or C existed;
- C did not know the Host had recovered through B;
- Host attention read local custody only when explicitly invoked.

Replacement therefore means choosing another independent custody relationship,
not transferring a global Porter office. An entirely unfamiliar custodian still
requires an out-of-band trust decision for its continuity root; cryptography
cannot authorize an unknown operator from nothing.

Existing AC responsibility prevents silently abandoning an accepted custodian's
outstanding copy. Sender policy can stop using A immediately, but A remains
responsible for prior ACs until each reaches CL or is lost. This is the general
post-AC release boundary found in the replicated-custody check.

## Fresh possession challenge

The honest experimental issuer accepts a nonce only after reading current inbox
bytes, recomputing the exact Package digest and matching its canonical AC. It
refuses after bytes disappear or after CL removes the Package from Porter
custody. Nonce replay and stale evidence keys fail verification.

That is a useful operational check, but the adversarial result is decisive:

**A dishonest holder of the evidence private key signed the same valid
POSSESSION_OBSERVATION after the inbox bytes were deleted. The verifier accepted
it.**

A signature authenticates testimony. It cannot prove the signing process read
storage. HMAC or encryption keyed by Package bytes does not solve this cleanly:
a custodian may retain only the derived challenge key. Probabilistic proofs of
retrievability require a separately designed encoding/challenge protocol.

For PORTER's exact immutable Packages, actual Collection is the strongest
existing possession test: it transfers and verifies the bytes. Fresh signed
observations may detect accidental loss by an honest implementation, but must
not be called trustless possession proof.

## Host-selected attention

All three custodians accepted while the Host performed no work. A later explicit
Host function inspected each local custody boundary and found three independent
`RECIPIENT_PORTER` states. Inspection caused no Porter-to-Porter communication
and no sibling names appeared in any custodian's local state.

This preserves the essential asymmetry:

```text
arrival changes Porter-local custody
Host-chosen attention learns selected local custody
arrival does not wake or notify the Host
```

A practical Host with several local Porter boundaries will need a Host-side
attention adapter that deduplicates exact Package identities before application
dispatch. That is scheduling/recovery tooling. It must not invent global custody
or application completion.

## Metadata and cost pressure

PORTER payload opacity is semantic, not confidentiality. Each custodian stored
and could read the full test payload. Plurality therefore reduces control and
availability concentration while multiplying disclosure surface.

Sequential isolated measurements for a 1 KiB payload were:

| custodians | AC + key setup + signed evidence | custody files | custody bytes | exported statements |
|---:|---:|---:|---:|---:|
| 1 | 6.509 ms | 6 | 55,996 B | 618 B |
| 3 | 15.314 ms | 18 | 167,988 B | 1,854 B |
| 5 | 24.347 ms | 30 | 279,980 B | 3,090 B |
| 9 | 44.694 ms | 54 | 503,964 B | 5,562 B |

The experiment includes per-store candidate infrastructure, so absolute bytes
are not a steady-state product estimate. The exact linear multiplication is the
important result. Real parallel carriage latency would depend on selected
responses rather than the sequential total.

Sensitive applications need end-to-end payload protection before multiplying
custodians. Even then, sender, recipient, Kind, size and timing remain visible
unless a later metadata-minimisation experiment changes carriage. Plurality is a
resilience/audit trade, not an unconditional privacy improvement.

## Authority boundary

No tested Porter could truthfully prove or decide:

- that it was the only, preferred or elected custodian;
- how many other copies existed;
- whether the Host had recovered elsewhere;
- whether another custodian was honest, reachable or current;
- whether the application processed the Package;
- whether its own signed possession claim was physically true to a hostile
  outside verifier.

Each could prove only its attributable historical statement. The Host/depositor
retained selection, comparison and recovery policy. This is the actual demotion:
plurality does not make Porters govern one another; it makes each Porter's claim
bounded enough to compare and replace.

## Falsified ideas

- Porters cross-checking one another as a route to trustworthiness;
- fresh signatures as cryptographic present-possession proof;
- using the Host identity as the evidence signer identity;
- reusing an operational carriage key as an evidence key;
- automatic trust of an unfamiliar replacement;
- global custodian election, replica state or healing;
- plurality as a privacy improvement without payload protection;
- putting custodian topology into Package correspondence semantics.

## Earned next experiment

Test **plural native carriage addressing**:

> Can one unchanged `Package.to` recipient be carried to several independently
> authenticated custodian identities and rendezvous histories, with each CU and
> returned AC evidence attributable to its actual custodian?

The falsification target should be that recipient identity can remain stable
while custodian routes are added, removed or replaced entirely in depositor
policy. No custodian should acquire Host authority or sibling awareness. Until
that survives native carriage, bounded plurality is proven at custody/evidence
level but not yet end to end.
