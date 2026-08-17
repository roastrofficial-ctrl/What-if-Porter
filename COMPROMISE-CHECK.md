# PORTER 1.2 — Capability Compromise Reality Check

PORTER 1.2 reproduced theft honestly: anyone holding the same HMAC capability
as Find Me is indistinguishable while that standing remains current. Before
remediation both the legitimate correspondent and attacker crossed AC. Custody
allowance bounded the resulting responsibility; it did not identify the moral
holder.

The experiment earned **standing succession**. An immutable standing-change fact
selects a prepared replacement Introduction or terminates the relationship.
Publication is the exact durable threshold. `IN`, LG, AC and CL are never
rewritten, and exact historical AC replay precedes current policy.

## Adversarial and crash results

- interruption after successor preparation leaves an inert candidate and old
  standing current after restart;
- interruption immediately after standing-change publication leaves only the
  successor current after restart;
- ordinary renewal prepares future standing without an authority overlap;
- termination leaves no authority for new AC but preserves historical replay;
- twenty attacker/change races linearised at the standing-change file: an old
  Package either obtained AC before it or was refused, and none crossed after;
- ten thousand attempts with old evidence after succession created no AC,
  inbox, refusal log or other durable recipient state;
- 40 old outstanding Packages would count against new standing; the executable
  constrained case filled an allowance, rotated and proved no reset until CL;
- narrowing from `hdbe.call` to `hdbe.info` changed only future admission;
- Passport absence blocked fresh claim verification but not ordinary old
  correspondence already supported by local truth.

## Isolated benchmark

Docker, `--network none`, 10,000 attempts, 100 standing changes:

| Case | Wall | CPU | growth | fsyncs |
|---|---:|---:|---:|---:|
| unknown stranger refusal | 265.36 ms | 265.17 ms | 0 files / 0 bytes | 0 |
| compromised old authority refusal | 335.40 ms | 335.34 ms | 0 files / 0 bytes | 0 |
| current authority acceptance | 11,878.18 ms | 3,615.27 ms | 20,000 files / 6,467,789 bytes | 40,000 |

Standing succession measured median 1.075 ms, p95 1.370 ms and p99 2.188 ms.
Process maximum RSS was 42,049,536 bytes. The compromised-known refusal was 1.26
times unknown refusal and about 35 times cheaper in wall time than authorized
acceptance. The pre-remediation blast-radius case accepted exactly its 50-Package
allowance; a legitimate holder using identical material was then refused too.

An initial implementation replayed the complete standing history after every
healthy change. One hundred changes caused 15,350 reads and median 3.02 ms. It
was rejected. Healthy succession now updates its in-memory projection directly;
restart alone reconstructs canonical history. The final 100-change run performed
no history reads on the healthy path.

## Real Butterfly proof

HarmonicDB remained `network_mode: none`. An attacker copied
`BUTTERFLY-PORTER-INTRODUCTION-1` and lodged
`PKG-ddd717d0d6f84c04b579a37dd555e96e`; HarmonicDB's Porter created
`AC-d447da4efc9b41c0896cd3b032a85ffc`. This was genuine authorized access, not a
fixture expecting refusal.

HarmonicDB then published `SC-ae5e4f023d6e4dc4b09328655bf96222`, selecting
`IN-a84bd69aaea345f9b339312effcabb40`; Find Me's reciprocal boundary published
`SC-1dbfb4b51a2f4668b4a033b128fcc3ef`. A new attacker Package under the stolen
old material received the deliberately undifferentiated public reason
`CORRESPONDENCE_NOT_ADMITTED` and created no AC. Replaying the exact earlier
Package returned the same historical AC.

The real Find Me Host then lodged `PKG-ed7a37a98fcd72fbd76edc85d542b919`
under replacement standing. HarmonicDB accepted it as
`AC-0ad458c603f74e78975a5e4674ee5030`, explicitly collected it as
`CL-c7ddcd8340e94a1cad4a27797a9fe0c0`, performed real HDBE audio-store growth,
and returned `HDB:00000002`. Find Me explicitly collected Return
`PKG-3ffdac1d26004f01b2b8b2bdb204b14e` as
`CL-560e585498059387fe250a0814df8c84` under reciprocal replacement standing.

## Pressure record

Standing stops being current when the recipient publishes the unique change
fact for its current predecessor. Renewal and compromise use the same mechanism;
their evidence, urgency and reason differ. The local recipient ceremony is
allowed to establish the threshold. This is deliberately not a correspondent
self-revocation signed only by the stolen capability.

Stale-compromise exposure remains from theft until the recipient learns and
publishes a change, or until expiry. Expiry therefore remains a useful maximum
staleness bound, not an instant notification mechanism. The experiment did not
need a mutable epoch counter: immutable Introductions already form generations
through their succession chain.

Public refusal does not reveal whether standing is unknown, expired,
superseded, narrowed, over allowance or supported by invalid proof. Legitimate
recovery receives less detail as the privacy cost. A callback-driven global
revocation service and per-Package Passport check were both tempting and
rejected: each would smuggle a live control dependency into ordinary admission.

The unexpectedly elegant result was that security succession and historical AC
replay coexist simply when policy governs only creation of new facts. The hard
part was making a ceremony atomic across crashes, races and separate local
processes without re-scanning history or resetting relationship responsibility.

The earned lesson is:

> Compromise cannot make old authority historically false. It can only establish
> a durable local boundary after which that authority creates no new truth.

No Web Servers, Continuous Correspondence and Porter-native carriage remain
visible and unimplemented.

## Exactly one next maturation experiment

Run **Standing Ceremony Correspondence**: determine how replacement authority
and compromise knowledge can reach two recipient-local Porters without trusting
the stolen capability to replace itself, adding a per-Package identity lookup,
or quietly inventing an unsolicited global control channel.
