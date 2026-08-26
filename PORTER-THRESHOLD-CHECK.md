# PORTER-THRESHOLD/1 — First check

Measured 24 August 2026. The experiment separates three claims:

1. several independently authenticated Porters reported durable acceptance;
2. at least one honest Porter held the logical correspondence at confirmation;
3. the correspondence is retrievable now.

The prototype proves the first when its evidence verifies. It supports the
second only under an explicit fault assumption. It does not prove the third.

## Reproduction

```sh
./tests/docker_threshold.sh
```

Six adversarial tests cover signed roster authority, distinct-witness counting,
forgery, duplicate votes, signed equivocation, independent Package identities,
roster rotation and post-confirmation withholding. The benchmark runs in a
Docker `--network none` namespace.

## Corrections required by the experiment

### Receipts need member signatures

Existing PORTER receipts are retained evidence learned through a carriage path,
but their JSON is not a member signature. An unsigned list of receipts can be
invented by the reconciler and cannot establish M independent witnesses later.

The prototype introduces a `WC-…` custody claim signed by each roster member's
Ed25519 custody key. It binds roster, logical deposit, logical digest,
constituent Package identity and digest, AC identity, acceptance time and state.
The roster must distinguish this signing key from an X25519 carriage key.

### The shared digest is not a PORTER Package digest

PORTER's existing `package_digest` covers the complete envelope, including its
`PKG-…` identity. N independent Packages therefore have N different digests.
The experiment observed three distinct constituent digests for a 3-member
deposit.

`TD` now defines a separate logical object containing its own identity, pinned
Roster, sender, recipient, Kind, timestamps and opaque payload. Its canonical
digest is shared in every constituent Package. Digesting only payload bytes
would permit context substitution; the full logical envelope must be bound.

### M-of-N has a fault model

M signatures establish at least one honest reporter only if fewer than M
roster signing identities are dishonest. They remove reliance on one specific
Porter; they do not remove trust “at all.” The result also depends on recipient
Standing governance, signing-key custody, and claimed operator independence.
Cryptography cannot prove that three identities are not controlled by one
company, administrator or machine.

For one tolerated dishonest or unavailable member, 2-of-3 is the smallest
useful rented arrangement: it can confirm with one member absent, and two
confirming signatures include an honest member if at most one is dishonest.
1-of-N retains single-witness trust. 2-of-2 resists one liar but cannot confirm
through one outage. These are assumptions, not Byzantine consensus.

## Reconciliation results

- A member identity counts once. Repeating its valid claim produces conflict,
  not a second vote.
- Changing the member name on a signed claim fails verification against that
  member's roster key.
- A member can sign a conflicting logical digest. The reconciler retains that
  valid equivocation as conflict and declines to confirm; it does not choose a
  payload.
- Every `TD` pins an exact `RS`. A later Roster cannot reinterpret outstanding
  claims, even if it is signed by the same Standing authority. New fan-out or
  migration requires a new logical deposit or an explicit future protocol.
- A `TC-CONFIRMED` is historical evidence that M members attested acceptance.
  All of them can later disappear, lose state or withhold. TC is not a lease or
  proof of present custody.

The proposal's `TC_WITHHELD` should therefore be a later observation linked to
the earlier TC, not a mutation or replacement of it. Failure to retrieve cannot
distinguish withholding, loss, partition or stale rendezvous.

## Collection correction

“M members' copies observed collected” and “a single collection verified
against the shared digest” describe different facts. One successfully verified
collection proves that the Host recovered the logical bytes; M historical
acceptances supplied redundancy before it. Requiring M Collections needlessly
transfers duplicate copies into Host custody and risks duplicate application
execution unless a logical-deposit deduplication boundary is invented.

`TR` should instead record one successful logical recovery, the exact member
and constituent CL used, and verification against the pinned TD digest. Other
copies remain independent Porter custody until explicitly collected or expired.
That recovery fact says nothing about whether the application processed the
payload.

## Isolated scaling result

The benchmark measures sequential local AC publication plus custody signing;
it is substrate work, not network latency. Real parallel fan-out latency tends
toward the M-th response rather than this sequential total.

| N | M | draft median | N AC + signatures | reconcile median | retained objects |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 0.039 ms | 6.611 ms | 0.112 ms | 1,980 B |
| 3 | 2 | 0.047 ms | 16.134 ms | 0.277 ms | 4,513 B |
| 5 | 3 | 0.064 ms | 26.098 ms | 0.444 ms | 7,046 B |
| 9 | 5 | 0.110 ms | 52.144 ms | 0.770 ms | 12,112 B |

CPU reconciliation and evidence size are linear in N. Durable constituent
acceptance dominates local cost. The byte figure includes TD, TC, constituent
Packages and signed claims, but excludes filesystem allocation and existing AC,
inbox and candidate projections; production storage cost will be higher.

## Implementation boundary

`porter.threshold` is an experimental pure protocol layer. It creates signed
Roster facts, pins a logical TD across N ordinary Packages, converts real
PORTER acceptance evidence into independently signed member claims, and
reconciles distinct claims into CONFIRMED, INSUFFICIENT or CONFLICT results.

It deliberately does not modify the daemon, automatically fan out, persist a
new canonical fact family, collect duplicates, infer operator independence,
retry, evict members or choose a Return roster. Those policies have not yet
earned a place in PORTER's custody lifecycle.

## Verdict

The mechanism is **supported after narrowing**. Signed, distinct M-of-N custody
claims can provide stronger historical evidence than one rented Porter's word,
and can remain opaque to application meaning. The original absolute claim is
**disproved**: THRESHOLD does not eliminate trust, unsigned receipts are not
threshold evidence, independent Package digests cannot be shared, and TC does
not establish current retrievability. With a pinned signed Roster, a separate
logical digest, member custody signatures and an explicit `f < M` assumption,
2-of-3 is a coherent first rented-tier experiment.
