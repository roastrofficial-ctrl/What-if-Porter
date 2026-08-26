# PORTER plural native carriage — first check

Measured 26 August 2026. This experiment attacks one proposition:

> Can every piece of network infrastructure presently carrying for a Host be
> replaced without changing Host identity, Package addressing, or requiring
> custodians to coordinate?

## Verdict

**Yes at native framing, custody and evidence level. Not yet through the
production `NativeCarriage` daemon.**

The experiment replaced every original custodian, recovered correspondence from
before and after replacement, restarted sender and recipient stores, and retained
attribution to the actual custodians. Every Package remained addressed only to
`harmonicdb`. No Package contained a custodian, endpoint, subset, replica count
or topology generation.

The decisive split is:

```text
outer authenticated CU:  alice → porter-b
encrypted inner Package: alice → harmonicdb
```

The network destination is a custodian presently willing to carry for
HarmonicDB. HarmonicDB itself has no network endpoint.

Existing `seal`/`open_frame` cryptography already supports this because CU AAD
binds its own `from` and `to` independently of encrypted content. The current
`NativeCarriage` class nevertheless passes one `Porter.identity` into both
layers and indexes one rendezvous by `Package.to`. The laboratory harness
separates them without changing PKG/LG/AC/CL. End-to-end daemon integration is a
future implementation experiment, not silently claimed here.

## Reproduction

```sh
./tests/docker_plural_native.sh
```

Seven hostile cases run in Docker `--network none`. They use real
PORTER-CARRIAGE/1 X25519/HKDF/AES-GCM frames, real Porter admission and AC, the
experimental evidence-key history, persistent CU queues, and real CL
publication. Frame transfer is an in-process laboratory transport rather than
the daemon's TCP server so the identity split can be tested without prematurely
changing production behavior.

## One Package, three CU destinations

One canonical Package was sent through three separately sealed Units:

```text
PKG-X { to: harmonicdb }
  ├─ CU-X-A { to: porter-a } → AC-A
  ├─ CU-X-B { to: porter-b } → AC-B
  └─ CU-X-E { to: porter-e } → AC-E
```

The Package JSON was byte-for-byte unchanged before and after fan-out. Each CU
used the selected custodian's X25519 public key and bound its custodian identity
in authenticated associated data. Delivering A's frame to B failed
authentication before durable state. Each returned AC was accompanied by a
signed statement binding `recipient: harmonicdb` and its distinct actual
`custodian`.

CU identities include Package plus custodian, because they name physical
carriage attempts. That distinction does not escape into correspondence:

```text
one PKG identity
many CU identities
many custodian-local AC identities
```

## The Alice/Bob falsification

Alice possessed only:

```text
harmonicdb → porter-a, porter-b
```

Bob possessed only:

```text
harmonicdb → porter-c, porter-d
```

The sets were disjoint. Alice lodged one Package and B accepted it. Bob lodged a
different Package and D accepted it. During one explicit Host attention
opportunity, the networkless Host collected Alice's Package from B and Bob's
Package from D.

No participant held a canonical global Host→Porter mapping:

- Alice knew A and B, not C or D;
- Bob knew C and D, not A or B;
- B knew its own carriage peer and local AC, not A/C/D;
- D knew its own carriage peer and local AC, not A/B/C;
- the Host knew only the two local boundaries it chose to inspect during that
  opportunity;
- neither Package named any of them.

The Host attention record is a laboratory observation, not a new global custody
fact. It says which local boundaries the Host inspected and collected in that
chosen visit. It does not declare the complete custodian set.

This is the important architectural result:

> Host identity and network topology are independent concepts.

## Independent authorization

Carriage authentication proves that bytes reached the selected custodian and
came from the named depositor carriage key. It does not itself authorize that
custodian to assume responsibility for a Host.

Each experimental custodian therefore retained independent existing PORTER
Standing for Alice and Bob. The per-custodian Package-bound admission proof
traveled inside the encrypted CU wrapper, not inside the Package. A frame
correctly addressed and encrypted to A but containing B's admission proof was
refused before AC.

Consequently three decisions remain separate:

1. depositor policy chooses a custodian destination;
2. CU authentication proves the physical carriage peers;
3. that custodian's local Standing decides whether it crosses AC for the
   unchanged Host recipient.

Different custodians may refuse, expire, narrow or succeed Standing
independently. None can authorize a sibling or speak for Host intent.

## Outstanding removal and late introduction

Alice queued independent CU attempts for A and B. B accepted while A's Unit
remained durable and outstanding. A was removed from Alice's current destination
knowledge. Restart preserved the unresolved A Unit rather than rewriting or
redirecting it.

Alice then introduced previously unused E and explicitly queued a new CU for the
same Package. E accepted under its own carriage key, Standing and evidence key.
The old A Unit did not automatically migrate or elect E as successor.

This preserves honest history:

- removal from current policy does not claim a prior attempt succeeded or
  failed;
- a new custodian produces a new CU and AC, not a new Package;
- retry state remains custodian-specific;
- automatic healing or redistribution was not invented.

A sender-side tool may eventually abandon a stale physical CU attempt. Such
abandonment changes local carriage intention, not Package or remote custody.

## Complete infrastructure replacement

Initial topology:

```text
Alice → A, B
Bob   → C, D
```

Replacement topology:

```text
Alice → E, F
Bob   → G, H
```

Old Alice and Bob Packages first reached B and D, then exact copies reached E
and G. New Packages reached F and H. Every A–D store and endpoint was destroyed.
One later Host attention opportunity recovered:

- old Alice correspondence from E;
- old Bob correspondence from G;
- new Alice correspondence from F;
- new Bob correspondence from H.

All four Packages retained `to: harmonicdb`. No successor custodian inherited an
old custodian's identity, AC or evidence key. Replacement changed only local
destination knowledge and physical CU attempts.

Thus the complete network infrastructure carrying for the Host was replaced
without renaming the Host or correspondence.

## Restart and historical attribution

After acceptance, both the recipient Porter store and depositor carriage process
were reconstructed. The depositor's retained evidence still verified through
the named custodian's evidence-key history and still identified `porter-b`, the
actual issuer. It did not degrade into the ambiguous statement “HarmonicDB's
Porter accepted.”

Outstanding per-custodian Units also survived sender reconstruction. Evidence
files are indexed by Package and custodian, preventing one custodian's response
from settling another custodian's attempt.

This depends on the evidence-identity succession result. A later production
design must durably retain or independently resolve those histories; endpoint
possession alone cannot authenticate old evidence.

## What the network knows

For a Package carried from Alice to B:

- observers of the native envelope see a protected Unit from `alice` to
  `porter-b`, its class, size and timing;
- B decrypts the Package and learns it is addressed to `harmonicdb`;
- the Package does not reveal A, C, D or Alice's destination policy;
- HarmonicDB has no listening socket, DNS target or carriage key;
- other custodians learn nothing unless separately selected.

This reduces the privileged statement “Porter B represents HarmonicDB” to the
narrower fact “Porter B accepted this exact correspondence for later local Host
attention.”

## What remains unresolved

### Production identity refactor

The harness proves the existing frame format can express the split. The daemon
still assumes:

```text
Package.to == Porter.identity == CU.to == rendezvous identity
```

Native integration must give a process a custodian/carriage identity while
allowing it to serve one explicitly configured Host recipient identity. AC may
remain recipient-local if returned signed evidence supplies custodian
attribution. This must be pressure-tested against ceremonies, admission,
Returns, refusal evidence and native evidence settlement before changing the
daemon.

### Local topology provenance

Alice and Bob began with locally trusted custodian keys and subsets. The test
does not explain how they discover a new custodian or decide it is authorized.
There must be no canonical global mapping, but local knowledge still needs
provenance, expiry and continuity. Existing per-identity rendezvous chains are a
candidate substrate; selection policy is not.

### Host access to several boundaries

The Host must be locally capable of inspecting selected Porter custody roots.
The experiment supplied those boundaries explicitly during attention. Dynamic
mounting, IPC authorization and removal without giving the Host a network
presence remain deployment questions.

### Disclosure multiplication

Every selected custodian still sees the Package metadata and clear opaque
payload. Plural carriage inherits the linear disclosure cost measured in the
plurality check. End-to-end payload protection remains strongly indicated.

## Falsified ideas

- custodian identity must appear in `PKG-*`;
- all depositors need the same Host→custodian set;
- the Host needs a globally canonical custodian roster;
- custodians must coordinate, reconcile or elect successors;
- replacing infrastructure requires Host or Package renaming;
- an outstanding CU must be silently redirected to a replacement;
- carriage authentication can replace recipient-local Standing;
- one acceptance response may settle every physical attempt for a Package;
- the network must contain an endpoint called `harmonicdb`.

## Earned result

The experiment supports the stronger PorterNet statement:

> The network does not contain HarmonicDB. It contains independently
> authenticated custodians presently willing and locally authorized to hold
> correspondence addressed to HarmonicDB.

Host identity lives in immutable correspondence. Custodian identity lives in
physical carriage, attributable evidence and depositor-local topology. Neither
needs to become the other.

The next justified work is a narrow **production NativeCarriage identity-split
experiment**, not a new correspondence protocol: introduce distinct configured
custodian and served-recipient identities, retain per-custodian evidence, and
rerun all native, Standing, ceremony, rendezvous and Host Runtime conformance
tests. If that refactor forces topology into Package or global sibling state,
the laboratory result must be revisited rather than protected.
