# PORTER-AUTHORIZATION/1 — verifiable correspondence check

Measured 26 August 2026. `PORTER-AUTHORITY/1` made current Standing and known
forks independently reconstructable, but deliberately left production admission
dependent on a shared HMAC secret. This experiment attacked whether exact
Package authorization can be verified without giving custodians sender-forging
capability.

## Verdict

**Both propositions survive in the laboratory. Verification can be separated
from manufacture, and one authorization proof belongs to immutable
correspondence rather than physical custodian topology.**

An Ed25519 sender authorization key signs one exact Package in one exact
authority/Standing context. Mutually unaware custodians verify with public
material. Compromise of every verifier, native key, custody store, configuration,
previous Package and proof does not produce the sender private key and cannot
authorize a new Package that a fresh custodian accepts.

Sender-key compromise remains powerful: it permits arbitrary cryptographically
valid Packages within that relationship until local authority succession makes
the key's Introduction stale. Recipient-derived Kind, size, expiry and custody
limits still constrain AC. A signature proves sender authorization, not
recipient permission.

This result is not productionized. It stops before replacing existing HMAC
Standing admission.

## Symmetric control

The existing production proof was tested first. A custodian configured with the
relationship HMAC secret verified a legitimate Package, then used the same
secret to construct a valid proof for a new custodian-manufactured Package. At
the Standing proof boundary the forged proof was indistinguishable from one
created by `find-me`.

HMAC is not weak. The semantic problem is that its verifier and prover possess
the same private capability. Compromise of a recipient custodian therefore
includes sender-impersonation capability for that relationship.

## Minimum asymmetric proof

The experimental `PACKAGE_AUTHORIZATION` binds:

| Bound value | Attack prevented |
|---|---|
| sender and recipient | relationship transplantation |
| Package identity and digest | reuse for another identity or changed immutable bytes |
| authority-root identity | transplant beneath another authority context |
| current Introduction | reuse after Standing/key succession |
| authorization-key identity and generation | key/context substitution |
| authorization proof identity and vocabulary | replay-safe domain separation |

The Package digest already covers Kind, payload, TTL, reply address and every
other immutable Package field. Each was altered after signing and verification
failed. The explicit sender, recipient and Package identity are intentional
context checks rather than substitutes for the digest.

Custodian identity is absent. Carriage route, native key and CU identity are
also absent. The same Package and proof therefore travel unchanged through any
selected custodian.

The proof does **not** contain recipient restrictions. Those come from the
trusted authority history for the named Introduction. A sender cannot grant
itself another Kind, larger Package, later expiry or more custody capacity by
signing such a claim.

## Compromise boundaries

### Custodian compromise

The attacker received everything A legitimately holds:

- native carriage identity and private key;
- custody database and configuration;
- public authority history;
- public sender verification key;
- prior Packages and authorization proofs.

It generated a new Package and signed with an attacker key while naming the
expected authorization-key identity. Fresh D rejected the signature. Native
carriage compromise could impersonate A as a transport peer, but could not
manufacture `find-me` correspondence authorization. These are independent
boundaries.

### Sender-key compromise

Possession of K0 allowed the attacker to authorize new `find-me → signing-host`
Packages. It did not let the attacker transplant authorization to another
recipient, change authority root, or widen recipient terms. A forbidden Kind
had a valid Package signature and was still refused by admission policy.

The experiment makes no claim that asymmetric senders are honest. It moves
forging capability from every verifier to the actual sender capability holder.

## Plural and disjoint topology

One Package and one proof verified independently at A, B and C. No secrets or
databases were shared. Verification was repeated after fresh construction of
D/E/F from public authority evidence alone.

Alice's proof verified unchanged at her locally selected A/B. Bob's independent
relationship proof verified at C/D. Neither proof named a custodian, sibling set
or canonical Host map. Authorization knowledge may be shared while topology
knowledge remains disjoint.

The depositor Porter need only carry an already authorized Package and proof. It
does not require the sender private authorization key and cannot authorize a
different Package merely by staging or retrying the first.

## Succession and key rotation

Standing moved:

```text
find-me remains find-me
IN-P0 / K0 → IN-P1 / K1
```

A stale custodian knowing only P0 admitted a valid K0 Package. An updated
custodian could still verify that K0 signed the Package, but returned
`REFUSED_STALE_AUTHORITY` for new AC. It admitted the corresponding K1/P1
Package. Sender correspondence identity did not become either public key.

There remains no global instant when K0 becomes unusable everywhere. Exposure
lasts until each relevant custodian learns succession or the predecessor terms
expire. This is the already known local-authority gap, not a cryptographic
failure hidden by online revocation.

## Known fork and replay

With portable history `P0→{X,Y}`, an X Package produced:

```text
proof_state     PACKAGE_SIGNATURE_VALID
authority_state FORKED
admission       REFUSED_AUTHORITY_FORK
```

The signature statement remains true; current recipient permission is
unresolved. Valid X, Y and predecessor proofs cannot create new AC once the fork
is known.

An exact Package accepted before fork knowledge retained its historical AC.
Retry with the identical digest returned `HISTORICAL_ACCEPTANCE_REPLAY` without
reevaluating present Standing. A changed Package with the same identity was
refused. This preserves PORTER's existing epistemic boundary.

## Fresh bootstrap and total infrastructure replacement

After one authority/key succession, A/B/C were treated as gone. D/E/F received:

- the independently trusted public `AUTHORITY_ROOT`;
- portable signed authority transitions;
- the sender public authorization key selected by current public terms;
- their own unrelated native/custody keys.

They received no A/B/C identity, database, HMAC secret or sender private key.
Each reconstructed P1, verified one unchanged K1 Package proof offline and found
it eligible for local AC. Host identity, sender identity and Package addressing
did not change.

The only private material crossing into replacement infrastructure is each new
custodian's own carriage/custody key. Sender private capability remains with the
sender-side signing environment.

## Deliberate production boundary

The laboratory separates:

```text
PACKAGE_SIGNATURE_VALID
        +
authority CURRENT/PENDING/FORKED/UNKNOWN
        +
recipient public restrictions
        +
custodian-local outstanding counts/bytes
        =
local AC eligibility or refusal
```

It does not yet wire this into `Admission.authorize`, native fan-out, or ceremony.
Doing so requires a migration story for existing HMAC Standing, durable retention
of Package authorization evidence, and exact crash/restart integration. Those
are production questions, not reasons to weaken the cryptographic result.

## What each participant can establish

### Sender

Possession of the private key permits authorization of exact Packages within the
scoped relationship. One signature binds exact immutable correspondence and an
Introduction/root context. It does not choose recipient restrictions or prove
that any custodian admitted the Package.

### Depositor Porter

It can lodge, fan out and retry Package plus proof without private sender
material. It knows what proof it carried, not whether the signer was wise or
whether every recipient admitted it.

### Recipient custodian

Public root/history/key material verifies the Package statement. Current local
authority knowledge, public terms and local custody accounting determine AC.
Compromise of the verifier does not provide sender-signing capability.

### Recipient Host

The networkless Host does not participate or become an online oracle. A local
sender-side Host may produce an authorized Package while offline; its Porter
later carries opaque bytes. The key is a relationship capability, not Host
identity.

### Fresh custodian

It becomes able to verify and decide local admission using public evidence plus
its own infrastructure secrets. It need not trust or contact an old custodian,
sender, authority, directory or Host during verification.

### Outside verifier

Given Package, proof, root and authority history, it can verify that the selected
sender key authorized exact bytes in the named context. It cannot establish AC,
durable storage, CL, Host observation, application processing, global authority
knowledge or absence of a hidden fork.

## Real-World Pressure Ledger

### Security

Public verification removes sender-impersonation power from compromised
custodians. Sender-key compromise remains a relationship-scoped authorization
compromise bounded by current recipient terms and local Standing knowledge.
Fork knowledge remains fail-closed for new AC.

### Availability

Verification is offline. Fresh custodians require no confidential material from
old infrastructure. Stale custodians may continue accepting K0 until they learn
succession; updated custodians continue under K1 without waiting for siblings.

### Trust

Fresh custody trusts a public authority root, signed history and the sender
public key selected by current terms. It trusts no other custodian's
interpretation. Sender private capability remains outside recipient custody.

### Privacy

The Package already reveals sender, recipient, Kind and payload to its receiving
custodian after carriage decryption. Portable proof additionally exposes the
authority root, Introduction, authorization-key identity and generation. An
outside verifier given the proof learns relationship and succession metadata.
Selective disclosure is not attempted.

### Operations

Custodian rotation changes no sender material. Sender-key rotation requires an
authority transition selecting a new public key. Standing changes alter public
terms/Introduction. Authority-root rotation remains unsolved and independent.
Operators must preserve proof alongside Package for later verification.

### Performance

Measured in the offline Docker image:

| Operation | Median |
|---|---:|
| existing HMAC proof | 0.007 ms |
| existing HMAC verify | 0.006 ms |
| Ed25519 Package sign | 0.058 ms |
| Ed25519 Package verify | 0.088 ms |
| verify unchanged proof at 3 custodians | 0.255 ms |
| verify unchanged proof at 9 custodians | 0.776 ms |
| derive length-1 authority + verify | 0.239 ms |
| derive length-10 authority + verify | 1.135 ms |
| derive length-100 authority + verify | 11.612 ms |
| derive length-1,000 authority + verify | 94.957 ms |

One authorization proof encoded to 585 bytes. Ed25519 is slower than HMAC by an
order of magnitude but remains sub-millisecond for ordinary verification.
Authority derivation should be cached as a disposable projection in production;
the benchmark intentionally reconstructs the full chain.

### Migration

Complete A/B/C→D/E/F replacement transferred only public relationship evidence.
No sender secret crossed the custody boundary. Production HMAC-to-signature
migration remains deliberately unimplemented.

### Evidence

Portable: sender key authorized exact Package bytes under named authority and
Introduction. Local: a custodian verified it and applied local limits. Separate
canonical facts remain AC, signed custodian claim, CL, Host observation and any
application result. None is implied by the Package signature.

## Stop condition

The experiment stops positively before productionization, key recovery, root
succession, PKI, selective disclosure or anonymous credentials.

The separation is real:

> **Correspondence authorization belongs to one immutable logical Package.
> Carriage may replicate that authorization without giving any custodian the
> ability to manufacture another Package as the sender.**

Cryptography establishes which scoped sender key authorized exact bytes. It
does not establish wisdom, global knowledge, current enforcement, custody,
collection or application processing.
