# PORTER 1.1 — Introductions Under Adversarial Lodgement

Measured 17 August 2026. Raw final evidence is
`benchmarks/results/porter-1.1-final.json`. PORTER/1's frozen LG → AC → CL
semantics remain defined by `CONFORMANCE.md`.

## What Introduction became

Introduction became an explicit, immutable, recipient-local `IN` fact plus a
separate possession capability. Explicit establishment won over first-Package
authority: it moves identity verification and larger claim evidence off the
hostile per-Package path, makes restart truth unambiguous, and permits Package
refusal through constant local work. First Package plus authority would make
strangers repeatedly buy claim verification from the recipient and blur failed
identity evidence with established standing.

Crossing AC requires all of:

- an exact recipient and syntactically valid Package;
- current `IN` standing for the claimed sender;
- an introduced Kind and enforced Package-size ceiling;
- an unexpired relationship;
- possession proof bound to the exact Package digest;
- available outstanding Package-count and byte allowance.

Technical Passport contributes offline-verifiable identity claims. Its existing
suite rejects forged, altered, expired, wrong-authority, revoked and replayed
proofs. An authority-neutral adapter hands PORTER only normalized subject and
issuer. PORTER deliberately does not ask Passport to choose Kinds, custody,
budgets, application meaning or AC. The real Butterfly currently provisions a
shared experimental capability with an offline-claim authority label; it does
not misrepresent that secret as a Passport credential.

An established Introduction continues when Passport is absent because its
verified result and capability are local. New Introductions fail closed when the
claim provider is unavailable. Global revocation and capability rotation were
not smuggled into this experiment.

## Adversarial result

| 10,000 attempts | wall | CPU | durable growth | new files | fsync |
|---|---:|---:|---:|---:|---:|
| Unknown/refused | 225.95 ms | 225.77 ms | 0 B | 0 | 0 |
| Authorized/accepted | 10.91 s | 2.86 s | 6,468,355 B | 20,004 | 40,000 |
| Unprotected acceptance control | 13.78 s | 3.07 s | 6,467,780 B | 20,000 | 40,000 |

Refusal was about 48 times cheaper than authorized acceptance and created no
recipient state proportional to attack volume. The full control was slower than
the secured run due to ordering/filesystem variance; it is not evidence that
security accelerates AC. The paired 200-sample distributions below are the
security-tax measurement.

| Cost | median | p95 | p99 |
|---|---:|---:|---:|
| PORTER 1.0 acceptance | 0.911 ms | 1.365 ms | 4.098 ms |
| PORTER 1.1 authorized acceptance | 1.034 ms | 1.865 ms | 5.065 ms |
| AC creation alone | 0.878 ms | 0.995 ms | 2.207 ms |
| standing lookup | 0.0004 ms | 0.0007 ms | 0.0020 ms |
| carriage proof | 0.0069 ms | 0.0108 ms | 0.0248 ms |
| policy evaluation | 0.0040 ms | 0.0055 ms | 0.0148 ms |

The measured median security tax is 13.5%. Durable AC/inbox publication remains
the dominant accepted cost.

Malformed envelopes, wrong Kind, unknown and known-but-unintroduced identities,
spoofed `find-me`, forged proof, expired standing, altered same-identity Package,
repeated exact identity, oversized authority, claim-provider absence, exhausted
count/byte allowance and 40 concurrent admissions were tested. Ten admissions,
not forty, crossed a ten-Package allowance.

A wire `Content-Length` above 256 KiB is refused before body acquisition. Within
that ceiling, the relationship's lower canonical-Package limit precedes proof.
This bounds the memory a 100 MB attempt can force. The remaining expensive
attack is a holder of a valid stolen capability: it may consume the entire
relationship allowance because PORTER cannot distinguish theft from its
correspondent.

## Replay, refusal and privacy

Exact replay recognizes historical AC before evaluating current standing. It
returns the same AC and creates no correspondence—even after Introduction
expiry. Changed bytes under the identity are refused. Replayed Introduction
evidence resolves to the same `IN`; changed terms cannot mutate it.

Refusal is evidence only that AC was not crossed under current recipient policy.
It does not mean recipient absence, application rejection or permanent refusal.
The recipient retains no per-attempt refusal history because that would recreate
the exhaustion vector. The originating Porter may retain one refusal against its
own Lodgement.

All standing failures expose the same public reason. This conceals whether the
recipient knows a sender, whether its Kind is introduced, whether standing
expired, and whether allowance is full. HTTP status still distinguishes malformed
wire/envelope (400), policy refusal (403), and oversized body (413), so some
boundary knowledge remains observable.

## Real Butterfly proof

Introduced Find Me lodged `PKG-7537a6c470323b6a550fcbc1666e9b52` for real
`hdbe.call` work. HarmonicDB's Porter proved standing, created AC, and the
networkless HarmonicDB Host later created CL and executed HDBE. Its Return
`PKG-98a2e761fb4c4cc18466ca6a32d8793f` crossed the reciprocal Introduction,
became AC at Find Me and was explicitly collected as
`CL-25bebb9c35ac752745345a6cece8f47e`.

The Host had no IP interface. Introduction, Passport absence and hostile traffic
did not wake it. A subsequent live attack sent 1,000 unknown identities, one
known-but-unintroduced identity, one proofless `find-me` spoof and one 300 KB
body: 1,002 policy refusals and one size refusal in 492 ms. HarmonicDB remained
at eight ACs and zero inbox Packages afterward.

## Pressure record

- Identity and permission remained distinct. Passport identity alone cannot
  cross AC.
- `IN` is historical because standing must truthfully survive restart. Later
  expiry does not rewrite it or old AC.
- Both count and bytes earned a place in custody allowance: count protects
  inodes; bytes protects disk and bounded parsing.
- Refusal evidence is useful to the sender but dangerous at the recipient, so
  only the sender retains it durably.
- The first budget projection was unexpectedly awful: rewriting all outstanding
  IDs made authorized admission O(N²). It was rejected and preserved in the
  calibration evidence.
- The unexpectedly elegant result was checking exact historical AC before
  current standing. Security policy can expire without making history lie.
- The unexpectedly difficult part was crash-safe allowance without turning the
  allowance itself into per-Package custody. A reconstructed in-memory counter
  plus compact periodic projection resolved it.
- A live Passport request per Package was rejected: it adds an inbound security
  dependency, makes outage deny established correspondence and creates a reason
  to wake or expose Hosts.
- Push, callback and Host policy evaluation were rejected outright under Host
  Isolation.

No Web Servers, Continuous Correspondence and Porter-native carriage remain
visible and unimplemented.

## Exactly one next maturation experiment

Run **Capability Compromise and Introduction Renewal**: steal an established
carriage capability, exhaust its allowance, then determine the minimum local,
offline-verifiable rotation and termination semantics that contain the damage
without rewriting `IN`, AC or CL and without introducing a live identity-service
dependency.
