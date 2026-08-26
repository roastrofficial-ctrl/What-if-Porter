# PORTER plural Standing — authority continuity check

Measured 26 August 2026. Production plurality left one singular seam: Standing
ceremony. This experiment asked whether mutually unaware custodians can each
learn and enforce recipient-local authority history without becoming a
distributed authorization cluster.

## Verdict

**Plural Standing works only while the ceremonial authority does not
equivocate. Existing PORTER can replay one honest history independently, but it
cannot derive a canonical current authority after an authorized fork.**

Temporary custodian disagreement is not itself unsafe or incoherent. During a
knowledge gap, each Porter correctly authorizes against the latest immutable
Standing Change in its own custody root. An unreachable or newly introduced
Porter can receive the original ceremony chain later, validate it against its
locally provisioned ceremonial grant, and derive the same current Standing. No
custodian coordination is needed.

The proposition fails when two properly authorized ceremonies name different
successors for the same predecessor. A may validly apply X while B validly
applies Y. A newcomer that sees X first becomes X-current and refuses Y as
stale; one that sees Y first becomes Y-current and refuses X. A later observer
holding both values can detect the fork, but neither branch nor existing
ceremony result proves which is globally current.

The smallest missing property is:

> **Portable, non-equivocating recipient-authority continuity—or explicit
> fail-closed fork knowledge—from a trust root independent of every custodian.**

This experiment stops there. It does not invent quorum, leader election,
sibling synchronization or a global current-Standing service.

## Reproduction

```sh
./tests/docker_plural_standing.sh
```

The four focused cases exercise deliberate divergence, predecessor compromise,
late and out-of-order replay, a new custodian, authorized forks, replay-order
dependence, and complete A/B/C → D/E/F infrastructure replacement.

## Honest independent history

All three original custodians began with independently established local
Standing for:

```text
find-me → signing-host
```

One identical ceremony value named the predecessor Introduction and one
successor Introduction. The value and proof were presented independently at A,
B and C. Each custodian created its own SC fact and result. Consequently their
SC identities and application times differed, while `cause`, predecessor and
successor agreed.

This distinction matters:

- the ceremony is the common authorized transition request;
- each SC is a custodian-local application threshold;
- there is no global ceremony result;
- one custodian's result says nothing about another's observation.

The forced sequence behaved honestly:

| Interval | A | B | C | Old authority | Successor authority |
|---|---|---|---|---|---|
| T0 | predecessor | predecessor | predecessor | AC at A/B/C | refused at A/B/C |
| T1 | successor | predecessor | predecessor | refused at A; AC at B/C | AC at A; refused at B/C |
| T2 | successor | successor | predecessor | refused at A/B; AC at C | AC at A/B; refused at C |
| T3 | successor | successor | successor | refused at A/B/C | AC at A/B/C |

Historical ACs created before a local SC remain true after succession. Replaying
the exact accepted Package still recovers the original acceptance rather than
retroactively applying new Standing.

## The predecessor-compromise window

After A applied succession, the predecessor credential was attacked at A, B and
C. A refused because its local SC had crossed. B and C legitimately crossed AC
because their current local Introductions still authorized the proof.

Plurality therefore does not create a novel kind of knowledge gap, but it
creates several independently exploitable instances and permits the last stale
custodian to extend the effective revocation window. Existing controls bound
each local exposure by Standing expiry, kind/size limits and custody allowance.
They do not establish a global instant after which the predecessor can obtain no
AC anywhere.

That statement becomes knowable only after inspecting every relevant custodian,
which conflicts with the absence of a canonical custodian set. PORTER must not
make it.

## Delayed custodian and newcomer

C remained stale while A advanced through two ceremonies. C later received the
second transition first and retained it as `PENDING_PREDECESSOR`. Delivery of
the original first transition applied and drained the pending successor. This
is safe because each value names an exact immutable predecessor and successor,
and the ceremony proof binds the complete value.

A new D behaved the same way without copying A's database or consulting any
custodian. This success has an important bootstrap condition: D was locally
provisioned with the original relationship Standing and ceremonial grant,
including verifier secrets, then received the original ceremony values and
proofs. Existing PORTER does not turn old IN/SC facts into publicly verifiable
authority objects. Its HMAC proof is symmetric, so a verifier also possesses
forging capability; authenticated native carriage supplies peer attribution
only during live delivery.

Thus existing history is replayable by a correctly bootstrapped recipient
Porter, but is not a self-authenticating portable chain that an arbitrary later
verifier can trust from disk alone.

## Authorized fork

Two ceremonies were constructed with:

```text
same recipient       signing-host
same sender          find-me
same predecessor     IN-original
different successor  IN-X / IN-Y
different ceremony   CM-X / CM-Y
valid authority      both
```

A applied X and B applied Y. Both branches admitted Packages using their own
successor credential and refused the other. When each later saw the conflicting
ceremony, its local predecessor slot was already occupied and it refused the
other branch as stale.

D replayed X then Y and ended at X. E replayed Y then X and ended at Y. The
current answer therefore depended on delivery order. Per-root atomicity prevents
a local fork; it does not prevent a recipient-authority fork across independent
roots.

An observer holding both original ceremony values can detect equivocation by
the shared predecessor and distinct successor/digest. Detection requires
obtaining both forks. Neither A nor B alone knows that a fork exists, and neither
can truthfully claim global canonicality. Existing storage also lacks a portable
conflict object for preserving both branches at one custodian: the second is a
stale refusal after the first occupies the predecessor slot.

## Total infrastructure replacement

Under a non-forking history, complete replacement works. A/B/C independently
applied one succession. D/E/F, with new roots and identities, independently
replayed the original ceremony, rejected predecessor proofs and admitted
successor proofs. Every A/B/C root was then destroyed.

The recipient remained `signing-host`; no Package or Standing fact named a
custodian. D/E/F converged without inheriting A/B/C identities or state. Combined
with the production plurality custody result, historical correspondence remains
recoverable wherever an actual replacement custodian holds it.

Under a fork, infrastructure replacement does not preserve a unique current
authority because none exists in the available evidence. Copying more custody
cannot manufacture the missing ordering.

## Custodian removal and physical retirement

Production ceremony carriage remains singular, so this experiment deliberately
did not implement plural ceremony Units after the authority fork falsified safe
generalization. If ceremony fan-out is later built, retiring B/C attempts may
only attest:

```text
DEPOSITOR_STOPPED_THIS_PHYSICAL_CARRIAGE_ATTEMPT
```

It cannot imply application, refusal, forgetting, agreement, or recipient-level
rollback. Package plurality already enforces this physical/semantic boundary.

## What each participant can establish

### Depositor

It knows which ceremony Units it lodged, which custodians returned local results,
and which attempts it stopped. Silence means unknown delivery/application. It
cannot infer propagation to unknown custodians or global predecessor revocation.

### Individual custodian

It knows its provisioned trust root, ceremony values it verified, its local SC
threshold and AC/refusal facts. Without seeing a competing branch it cannot know
that authority forked or that its branch is global.

### Recipient Host

The networkless Host sees collected correspondence at the custody roots it
chooses to inspect. It does not participate in ceremony and cannot infer global
Standing from Package arrival. Conflicting admissions may be observed as
correspondence, not automatically interpreted as authority consensus.

### Newly introduced custodian

With trusted bootstrap material and one non-forking chain, it can independently
derive current local Standing. With two forks, first-observed order chooses its
local branch. Without trusted bootstrap material, existing IN/SC files and HMAC
proofs are insufficient to establish authority independently.

### Later outside verifier

It can compare supplied immutable values and detect two successors for one
predecessor. It cannot know a hidden fork does not exist, cannot validate HMAC
authorship without shared secret, and cannot turn a local result into proof of
global propagation or canonical current authority.

## Real-World Pressure Ledger

### Security

Plurality extends stale-authority exposure until each selected custodian learns
succession or its predecessor Standing expires. A compromised ceremonial
authority can fork independent custodians, and per-custodian transition limits
are not a global limit. Native origin authentication protects live carriage but
does not make retained symmetric history publicly verifiable.

### Availability

Honest ceremony does not require every custodian online. Updated custodians may
continue serving successor-authorized correspondence while stale ones apply
their prior rules. Requiring global revocation before operation would reintroduce
a roster and availability coupling. Fork detection, however, must fail closed
once both branches are known.

### Trust

A newcomer must trust locally supplied bootstrap Standing and ceremonial grant,
plus authenticated delivery of the transition chain. It need not trust A/B/C's
opinion. PORTER presently lacks an independently verifiable, non-equivocating
recipient-authority root suitable for arbitrary later bootstrap.

### Privacy

Every selected custodian learns the relationship identities, allowed Kinds,
budgets, expiry, succession reason and replacement possession material. Plural
Standing multiplies this disclosure. The current ceremony even carries the
replacement operational secret inside each encrypted CU.

### Operations

Operators can monitor outstanding custodian-indexed attempts and compare
returned local results without declaring consensus. Stale custodians are visible
only relative to the depositor's local selection. Fork monitoring may collect
evidence, but must not silently elect a branch or become protocol authority.

### Performance

An honest chain of length L across N custodians costs O(NL) carriage,
verification, immutable facts and local projections. Out-of-order delivery adds
bounded pending storage. No coordination round is required in the non-forking
case.

### Migration

Complete custodian replacement succeeds for a single history with explicit
bootstrap trust and replay. It fails to yield a unique authority under an
undecided fork. Host and Package identities remain unchanged in both cases.

### Evidence

Existing evidence distinguishes ceremony issuance/lodgement at the origin,
observation and SC application at an individual custodian, and returned local
result. It cannot prove all-custodian propagation. Holding both ceremony forks
detects equivocation, but current HMAC evidence is not portable to an untrusted
outside verifier and no canonical winner follows from detection.

## Stop condition

The experiment rejects both extreme conclusions.

Plural Standing is **not** inherently a distributed authorization cluster:
independent delivery of one non-equivocating history works, tolerates delay and
supports total infrastructure replacement.

But existing PORTER cannot safely call that history globally current under
authorized equivocation. Before production ceremony fan-out, PORTER needs a
separate experiment into non-equivocating, portable recipient-authority
continuity and fail-closed fork evidence. Designing that mechanism here would
protect the desired outcome rather than earn it.
