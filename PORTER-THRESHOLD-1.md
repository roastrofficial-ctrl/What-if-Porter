# PORTER-THRESHOLD/1

## Motivation

Every prior generation treats the Porter as limited but honest. LG, AC, and CL
give a Host provable custody history — provided the Porter that recorded each
fact was telling the truth. A rented Porter breaks that assumption. It is
infrastructure operated by a third party, sitting between every depositor and
the Host, and it can lie about receipt, silently drop a Package, delay it
selectively, or claim custody it never actually held. Nothing in PORTER/1
through 1.5 gives a Host a way to detect this, because nothing requires more
than one Porter to agree.

THRESHOLD does not make any single Porter trustworthy. It removes the
requirement that any single Porter be trusted at all.

## Scope

- Applies only where the sending Host maintains, at deposit time, a Roster of
  N independently operated Porters authorized to carry correspondence for a
  given recipient identity.
- Does not replace LG/AC/CL. Every constituent deposit remains ordinary
  PORTER/1 correspondence with its own Lodgement, Acceptance, and Collection
  lifecycle.
- Does not attempt Byzantine consensus on payload content. THRESHOLD
  reconciles claims about *custody*, never application meaning — consistent
  with "correspondence ends where meaning begins."

## The Roster

A `RS-…` Roster fact is a signed, versioned list of Porter identities
empowered to carry correspondence for a recipient:

```
{
  "roster": "RS-…",
  "recipient": "…",
  "members": [
    { "porter": "…", "endpoint": "…", "pubkey": "…", "weight": 1 }
  ],
  "threshold_m": 2,
  "effective_from": 0,
  "signed_by": "<recipient Standing key>"
}
```

A Roster is itself a Standing-governed fact (see STANDING-SUCCESSION) and
follows the same succession rules as any other recipient-local claim of
authority. A depositor resolves a Roster before a threshold deposit exactly
as it resolves an ordinary Porter address today.

## Threshold Deposit

One logical Package is fanned out as N independent PORTER/1 deposits, each
carrying the same payload digest but its own Package identity and envelope.
The sender's local client retains a `TD-…` fact recording which underlying
`PKG-…` identities correspond to which roster members and the shared digest.

```
Sender Host
    │ TD (local, private)
    ▼
 fan-out ──▶ Porter A  (independent PKG, RECEIPT)
         ──▶ Porter B  (independent PKG, RECEIPT)
         ──▶ Porter C  (independent PKG, RECEIPT)
```

## Reconciliation

The sender does not trust any single RECEIPT. It collects receipts from
reachable roster members and, once at least M report `HELD_FOR_COLLECTION`
with a matching digest, records a canonical `TC-…` (Threshold Confirmed) fact.
If M cannot be reached before expiry, the fact becomes `TC_INSUFFICIENT` — a
record that the roster did not corroborate custody, not an accusation against
any member.

Recipient-side reconciliation mirrors this on Collection: the recipient Host
may collect from any subset of roster members holding the digest. A `TR-…`
fact attests reconciled collection once M members' copies have been observed
collected, or a single collection has been cryptographically verified against
the signed digest shared by the others.

## Divergence

- **Conflicting digests** for the same claimed Package identity across
  members produce an immediate `TD_CONFLICT` fact. Evidence is retained
  unmodified; no automatic reconciliation is attempted; the application
  decides what to do with it.
- **Silent withholding** — a Porter reports a RECEIPT but cannot later
  produce the content on Collection — produces `TC_WITHHELD`. This does not
  accuse the Porter of malice; a partition and a lie are indistinguishable
  from outside the Porter.

## What THRESHOLD does not know

- Whether a divergent Porter is compromised, buggy, or merely partitioned.
- Whether M-of-N corroboration implies the payload is semantically correct —
  it implies only that M independent parties hold the same bytes.
- Whether a member should be evicted or down-weighted after divergence. That
  is a Roster governance decision, made explicitly by the Host's operator via
  a newly signed Roster fact — never an automatic protocol action.

## Invariants

- No single Porter's word is canonical for custody; only a reconciled
  threshold fact is.
- A Roster is signed by the recipient's Standing key and is a
  succession-governed fact like any other.
- Divergence between members is retained as evidence, never silently
  resolved or hidden.
- THRESHOLD adds no new payload semantics; payload stays opaque to every
  Porter and to the reconciliation logic itself.
- `TD`, `TC`, and `TR` facts are immutable historical facts, exactly as `LG`,
  `AC`, and `CL` are.

## Historical lesson

> A single witness is testimony. M-of-N witnesses are evidence.

## Open questions for the THRESHOLD experiment

- Cost and latency scaling with N; minimal viable N for a rented tier.
- Interaction with RENDEZVOUS-CONTINUITY when roster membership changes
  mid-flight of an outstanding threshold deposit.
- Whether a Return should default to the same roster as the originating
  deposit, or may travel through a smaller, independently chosen roster.
