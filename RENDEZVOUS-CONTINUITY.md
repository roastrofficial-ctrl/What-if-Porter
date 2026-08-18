# PORTER 1.5 — Rendezvous Knowledge and Identity Continuity

PORTER keeps five concepts separate:

```text
identity     enduring name of the intended Porter
rendezvous   locally retained evidence of one current approach
location     lower-level host and port named by that evidence
route        the attempt selected from current local knowledge
transport    disposable framed TCP byte movement
```

## The 1.4 cheat

In 1.4, `--native-rendezvous` statically associated a Porter identity with a
Docker DNS name, port, and X25519 public key. Docker supplied name-to-container
plumbing. PORTER treated the configured dictionary key as semantic identity,
the X25519 key as cryptographic trust, and the host/port as location. A human
had to replace all three values when a peer moved.

1.5 retains that map only as local generation-zero bootstrap knowledge. It is
materialised as an `RV-…` `LOCAL_GENESIS` fact. It is not queried again as a
live registry and it is not correspondence history.

## The fact the experiment earned

A later `RV-…` is an immutable `PORTER-RENDEZVOUS/1`
`RENDEZVOUS_TRANSITION`. It names the enduring Porter identity, monotonic
generation, exact predecessor `RV`, location, operational X25519 carriage key,
activation/expiry, and an Ed25519 signature from a separately established
continuity authority.

The `RV` identity derives from the canonical unsigned content. The signature
therefore binds identity, predecessor, generation, location, key, and validity.
The continuity authority is not correspondence standing, a carriage key,
Technical Passport, DNS, or endpoint possession.

The current X25519 key proves and protects ordinary carriage for one generation.
It is not the Porter identity and may disappear. The configured Ed25519 public
root verifies transitions locally and is absent from ordinary Package admission.

## Becoming current

Verification happens before durable state. A transition becomes current only
when its predecessor is known, its generation is predecessor + 1, activation
has arrived, and no other valid successor occupies that slot. The immutable fact
is the threshold; `rendezvous/current/<identity>.json` is rebuildable.

Authentic replay cannot move the projection backwards. Valid out-of-order
evidence is refused without storage and must be replayed after its predecessor;
this avoids a hostile pending-evidence inode queue. Two valid successors prove
authority equivocation. Both bounded facts remain, but local knowledge becomes
`CONTINUITY_CONFLICT_OBSERVED` and carriage is suspended. Arrival time and
remote timestamps never choose a winner.

A future announcement is an immutable promise, not a mutable DNS record. A
purported cancellation/replacement in the same predecessor slot is a conflict.
A later transition can be issued after the announced generation becomes current.

## Learning and recovery

Signed transition evidence can be pre-announced through native carriage during
overlap. It can also arrive as a bounded signed native frame after the old
location and operational key disappear. It needs no central lookup and no trust
in the delivering endpoint: acceptance uses the already-retained continuity
root and predecessor chain.

An outgoing Package remains unchanged while knowledge is stale. Failure at a
known location records only `KNOWN_RENDEZVOUS_ATTEMPT_FAILED`; it does not claim
the Porter is absent, its identity invalid, or standing expired. Missing,
expired, or conflicted knowledge prevents an attempt and retains the Unit.

Expiry says the last approach is no longer claimed current. Porter identity,
historical `RV` facts, standing, and correspondence remain known.

## Disaster boundary

No automated claim can manufacture continuity after the established Ed25519
authority is lost, or safely repair it after that authority is stolen. Recovery
then requires explicit recipient-local re-identification of the continuity root.
Existing `IN`, `SC`, `LG`, `AC`, `CL`, `CM`, Package, and historical `RV` facts
remain history.

The laboratory uses fixed continuity keys in Compose. Production root custody,
root succession, and local re-identification are deliberately not claimed.
