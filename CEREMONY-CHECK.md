# PORTER 1.3 — Standing Ceremony Correspondence Reality Check

PORTER 1.3 removed the 1.2 god-hand by making compromise knowledge travel as a
durable, separately authorized ceremony addressed to the recipient Porter.
Operational authority and ceremonial authority separated under the
anti-circularity attack.

The durable facts are an immutable bounded `CG-…` recipient-local grant, the
origin's immutable CM lodgement, the recipient's exact presented CM evidence,
the candidate immutable IN, and the decisive immutable SC. Ceremony results and
outbound-current files are recoverable knowledge/projections. No ordinary AC or
CL is created because the Host is not the recipient.

## Security and recovery results

- stolen operational possession could create ordinary AC but could not forge a
  ceremony proof;
- term widening, wrong relationship, wrong recipient, identity collision and
  oversized ceremony were refused before durable facts;
- a stolen ceremonial key could replace or terminate operational standing only
  within one finite grant; it could not widen terms, reset custody, target
  another relationship or exceed the change allowance;
- exact duplicate ceremony reproduced one result; changed bytes under the same
  CM identity were hostile;
- a ceremony for an unknown successor predecessor waited within a bounded
  pending allowance, then applied after its predecessor arrived;
- replay from every historical generation neither forked nor reversed standing;
- twenty ceremony/attacker races linearised at recipient-local SC;
- recipient absence preserved origin lodgement and left application standing
  unchanged; later exact carriage completed it;
- crashes after origin lodgement, outgoing materialisation, recipient evidence,
  verification, candidate IN, SC and result all reconstructed one explainable
  standing state;
- losing the result after remote SC left origin knowledge unknown; repeating CM
  reproduced the result and repaired outbound knowledge;
- exact historical AC replay remained valid after ceremony and termination.

## Isolated benchmark

Docker with `--network none`, 10,000 hostile attempts and 100 valid changes:

| Case | median / wall | CPU | durable growth | fsyncs |
|---|---:|---:|---:|---:|
| invalid ceremony refusal ×10,000 | 230.59 ms | 229.80 ms | 0 files / 0 bytes | 0 |
| ordinary unknown refusal ×10,000 | 169.42 ms | 169.32 ms | none measured | none |
| origin durable CM preparation | 1.555 ms median | — | included below | included below |
| ceremony proof verification | 0.0089 ms median | — | 0 | 0 |
| recipient verification + IN + SC + result | 3.378 ms median | — | included below | included below |
| total without transport delay | 4.854 ms median | — | — | — |

Valid total p95 was 11.216 ms and p99 17.612 ms. One hundred ceremonies added
701 files and 347,060 bytes and performed 1,200 fsyncs. Process maximum RSS was
24,391,680 bytes. Invalid ceremony was 1.36 times ordinary unknown refusal and
created no state proportional to attack volume.

The initial finite-grant implementation scanned every historical SC on each
change: 100 ceremonies caused 5,150 reads. It was rejected. Restart now rebuilds
the use count once and the healthy path increments it; the final run performed
200 reads, the fixed duplicate/predecessor checks rather than a growing scan.

## Real Butterfly knowledge gap

Find Me and HarmonicDB began with current operational standing
`IN-a84bd69aaea345f9b339312effcabb40`. The stolen capability created
`PKG-0e99b6d52e484b91b15a745623692431` and
`AC-f24ab94aa34f45ce8a6e616c19ade3c4` before compromise knowledge.

Find Me knew compromise and durably lodged
`CM-40695478bb9445d6bd2782e88486c8c2` at `1786976012092` ms while its Porter
carriage was deliberately stopped. During that gap, the attacker created
`PKG-56bc1a7c3de648d8ab6519cdfe23a155` and
`AC-07ae20cad1384b78bb73a1757ce0d824`. That AC remains valid history.

After carriage resumed, HarmonicDB retained the ceremony at `1786976037231` ms,
prepared `IN-0ffcc6a2a36846118e0b37920c026784` four milliseconds later and
published `SC-224d67d197cc463f86432acad6cf0bb3` three milliseconds after that. The
known-to-SC exposure was 25.146 seconds: 25.139 seconds before recipient
knowledge and seven milliseconds of recipient evaluation. Find Me retained the
APPLIED result 59 milliseconds after SC. A new old-capability Package was then
refused before AC.

Find Me updated only its outbound credential knowledge from the result. It did
not invent reciprocal standing. Its real Host lodged
`PKG-fe0df1bab8c2bbd588667a8d57f4621e`; successor standing created
`AC-c0a017d76fac432fada50de5b5d48fb2`. Networkless HarmonicDB explicitly
collected it, performed real audio-store growth as `HDB:00000003`, and returned
`PKG-5be302825ce24b82a5fbde0ee9054e80`. Find Me explicitly collected that Return
as `CL-9804ba0453746d206307f27889df5c65`.

Exact replay of the gap Package returned the original `AC-07ae20…`. Duplicate
replay of the old CM returned the original `SC-224d67…` result and did not move
current standing backward. HarmonicDB remained `network_mode: none` throughout.

## Pressure record

Compromise knowledge travelled as canonical CM evidence plus a proof under a
pre-established CG. Its computational recipient was the Porter. The remote
evidence justified reconsideration; only the recipient-local SC changed truth.
Passport remained absent from every ordinary Package and from the live ceremony
because the bounded grant had already been established locally.

Packages accepted before recipient SC remain valid because sender knowledge
cannot retroactively become recipient knowledge. The origin knows remote action
only after retaining the ceremony result. If the result is absent it knows
lodgement and attempts, not whether SC exists; exact replay repairs this but
does not make synchronous certainty.

The unexpectedly elegant result was the existing predecessor transition slot:
it supplies replay, deduplication, ordering and fork prevention without clocks
or consensus. The unexpectedly difficult result was separating outbound
credential knowledge from reciprocal inbound standing—symmetry had concealed
that category error until one-way ceremony made it observable.

The earned lesson is:

> Security knowledge changes remote authority only after it completes a journey
> into recipient-local evidence; everything accepted before that threshold
> remains the history the recipient was entitled to create.

## Exactly one next maturation experiment

Run **Porter-native carriage**: design carriage around durable identity,
recipient-local thresholds, asynchronous result knowledge and protected
Porter-to-Porter evidence, then test whether endpoint, connection and synchronous
HTTP assumptions can be removed without weakening any PORTER invariant.
