# PORTER NativeCarriage identity split — production check

Measured 26 August 2026. The plural carriage laboratory separated:

```text
served recipient identity = harmonicdb
custodian identity        = porter-b
```

This check forces that distinction through the production `NativeCarriage`
implementation and existing PORTER semantics. The change is retained only if
Package, Standing, ceremony, Return, refusal, rendezvous, restart, Host Runtime
and frozen conformance remain coherent.

## Verdict

**The production stack survives. Recipient identity and Porter custodian
identity do not have to be the same thing.**

All 199 unit/conformance cases and all six frozen Docker generation journeys
passed. The focused split suite used actual loopback TCP inside Docker
`--network none` and exercised every requested lifecycle.

This earns the foundational invariant:

> **A Porter speaks for its custody, never for the Host.**

The network-facing process authenticates as `porter-b`; correspondence remains
addressed to `harmonicdb`; the Host remains networkless. Equality remains the
backward-compatible configuration default, not a protocol requirement.

## Reproduction

```sh
./tests/docker_native_identity_split.sh

# Frozen Generations I–VI were also run:
for generation in 1 2 3 4 5 6; do
  ./tests/docker_generation${generation}.sh
done
```

## The production split

`Porter.identity` continues to mean the served recipient for existing Host-side
and correspondence behavior. `NativeCarriage.identity` may now be configured as
a distinct custodian identity:

```text
Porter.identity                   harmonicdb
NativeCarriage.identity           porter-b
NativeCarriage.served_recipient   harmonicdb
```

Outbound destination selection is an explicit local map:

```json
{"harmonicdb":"porter-b"}
```

Rendezvous knowledge is keyed by `porter-b`, not `harmonicdb`. The Package is
unchanged:

```json
{"from":"find-me","to":"harmonicdb","package":"PKG-…"}
```

The resulting authenticated layers are:

```text
PORTER-CARRIAGE/1 envelope
  from: porter-a
  to:   porter-b
  class: PACKAGE

encrypted value
  Package.from: find-me
  Package.to:   harmonicdb
```

The CLI exposes the distinction as:

```text
--identity harmonicdb
--native-custodian-identity porter-b
--native-recipient-custodians '{"find-me":"porter-a"}'
--native-rendezvous '{"porter-a":{...}}'
```

If the new options are absent, custodian identity defaults to `Porter.identity`
and recipient destination defaults to the recipient itself. Every prior native
configuration therefore retained its old behavior.

## Package, AC and attribution

Find Me lodged an unchanged Package to `harmonicdb`. The CU traveled from
`porter-a` to `porter-b`. HarmonicDB's Porter applied ordinary admission and
published the unchanged AC:

```text
AC.recipient  = harmonicdb
Package.to    = harmonicdb
CU custodian  = porter-b
```

The returned receipt retained `recipient: harmonicdb`. A separate local native
attribution observation recorded that `porter-a` authenticated evidence from
`porter-b`. Custodian identity therefore does not contaminate canonical AC or
ordinary Package evidence.

Attribution is currently local authenticated carriage evidence, not an
independently signed custodian statement. The earlier evidence-identity
experiment remains the route to third-party-verifiable attribution. This check
does not falsely upgrade transport authentication into a portable signature.

## Evidence settlement exposed and repaired one hidden assumption

With a singular recipient, an acceptance response implicitly came from the only
possible peer. Split identities make that unsafe. A different known custodian
could otherwise send a syntactically valid response naming the same Package.

Production settlement now checks:

```text
response outer origin == outstanding CU.to custodian
```

A forged acceptance response authenticated as `porter-c` could not settle the
Package Unit queued to `porter-b`, created no receipt, and left the real attempt
outstanding. Duplicate evidence from the already attributed custodian remains
idempotent.

This is not quorum or global state. It is local correlation between one physical
attempt and its authenticated peer.

## Standing and refusal

Standing remains defined between correspondence identities:

```text
sender:    find-me
recipient: harmonicdb
```

The admission proof travels inside the encrypted CU wrapper. The native outer
identities do not grant application standing. A valid CU from `porter-a` carrying
a forbidden Package Kind was refused before AC, and the refusal returned from
`porter-b` to `porter-a` while still naming the original Package.

Thus:

- carriage identity authenticates the transport peers;
- Standing authorizes the correspondence relationship;
- AC records recipient-local responsibility;
- none substitutes for another.

## Ceremony

A complete Standing succession ceremony traveled:

```text
outer CU: porter-a → porter-b
inner CM: find-me → harmonicdb
```

HarmonicDB applied the successor Introduction and returned the ceremony result
through `porter-b → porter-a`. Existing predecessor, authority, terms, replay and
atomic SC behavior remained unchanged. Local attribution retained the actual
custodian that returned the result.

No ceremony granted `porter-b` authority over HarmonicDB identity. The
custodian merely carried an independently authorized recipient-local change.

## Host Runtime and Return

The networkless HarmonicDB Host Runtime inspected the unchanged local Porter
root, crossed CL, and dispatched the original Package to its adapter. It knew
only:

```text
host = harmonicdb
Package.to = harmonicdb
```

It required no custodian identity and no network topology.

HarmonicDB later lodged an ordinary Return:

```text
Package.from = harmonicdb
Package.to   = find-me
in_reply_to  = original PKG
```

Its outer CU traveled `porter-b → porter-a`. Find Me accepted and collected it
normally. Application correlation remained Package-based; carriage topology did
not enter the Return.

## Rendezvous continuity

The depositor initially knew the old approach for `porter-b`, not an endpoint
for HarmonicDB. The old endpoint died while an unchanged Package remained
outstanding. Attempts recorded known rendezvous failure without changing the
Package.

The replacement `porter-b` endpoint sent a continuity-authorized transition to
`porter-a`. Find Me learned the new `porter-b` location and operational key,
retried the unchanged Package, and obtained AC at the same served recipient
`harmonicdb`.

The independent continuities are now correctly named:

- Host/correspondence identity continuity: `harmonicdb` in PKG/Standing/AC;
- custodian network continuity: `porter-b` in RV/CU;
- application continuity: outside PORTER carriage.

Moving or rotating the custodian no longer pretends that HarmonicDB moved on the
network.

## Restart and old evidence

After successful carriage, `porter-a` restarted with the split configuration.
It reconstructed:

- served recipient `find-me`;
- custodian identity `porter-a`;
- recipient destination `harmonicdb → porter-b`;
- custodian-indexed rendezvous knowledge;
- existing AC receipt bytes unchanged;
- native custodian attribution bytes unchanged.

The refactor did not rewrite old receipts to inject topology. This matters for
historical verification and exact replay. Existing equality-mode evidence also
continues to load because new attribution is separate and the default identities
remain equal.

## Frozen conformance

The complete 199-test suite passed after the split, including the earlier:

- LG/AC/CL and crash thresholds;
- Introductions and Standing succession;
- ceremonies and compromise response;
- native hostile framing;
- rendezvous movement, replay and conflict;
- Host Runtime scheduling, recovery and adapter boundaries;
- attestation, replicated custody, plurality and negative THRESHOLD checks.

Docker Generations I–VI also passed unchanged. Their Hosts remained networkless.

No conformance proposition required `recipient == custodian`. The equality was
an implementation convenience in native routing.

## Deliberate boundary: this is identity split, not production fan-out

Production currently maps one served recipient to one selected custodian at a
time. It does not yet:

- queue several custodian-specific CUs automatically;
- retain several independently returned AC receipts for one Package;
- expose sender-side custodian-set policy;
- replace an already accepted custodian's evidence with another;
- perform healing, quorum or global reconciliation.

Those are plurality tooling concerns. The previous laboratory proved their
ontology, but this surgical change does not smuggle them into `NativeCarriage`.
In particular, existing Package-keyed outgoing and receipt paths would need
explicit custodian dimensions before true production fan-out. That work must be
separately pressure-tested.

## Falsified ideas

- `Package.to` must equal the native frame destination;
- a Porter daemon must authenticate on the network as its served Host;
- Standing sender/recipient names must be CU peer names;
- ceremonies require recipient and custodian identity equality;
- Returns must traverse the same semantic identity as their CU endpoints;
- Host Runtime needs to know which custodian carried a Package;
- rendezvous movement means the Host moved;
- old evidence must be rewritten after an identity split;
- any authenticated custodian may settle another custodian's outstanding Unit.

## Foundational conclusion

PORTER can now state without qualification:

> **Hosts have no network presence. Custodians do. A Porter speaks only for the
> custody and carriage facts it actually establishes; it never represents Host
> identity, intent, application state or global availability.**

The network may contain `porter-a` and `porter-b`. Correspondence may name
`find-me` and `harmonicdb`. The two identity systems meet only at explicit local
carriage selection and recipient admission boundaries.

The next work, if chosen, is no longer to prove the distinction. It is to mature
production plural selection and custodian-indexed attempt/evidence storage while
preserving this invariant. No new Package abstraction has been earned.
