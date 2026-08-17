# PORTER Standing Succession/1

An Introduction is an immutable historical fact. It says that a recipient
established standing for a sender under particular authority and terms. It does
not say that standing remains current forever.

Current standing is reconstructed by beginning at the relationship's first
`IN-…` and following immutable `PORTER-STANDING/1` change facts. Each change
names exactly one predecessor and either one successor Introduction or no
successor. No predecessor has more than one transition slot.

```text
IN-OLD ── SC { successor: IN-NEW } ──> IN-NEW
IN-NEW ── SC { successor: null } ────> no current standing
```

The `SC-…` identity names the event. Its canonical file is named by the
predecessor, making a fork both invalid and detectable in one local lookup.
Publishing that file atomically is the sole threshold: before it, old evidence
may create AC; after it, old evidence may not create a new AC and replacement
evidence may. Candidate successor Introductions are inert until that threshold.

The same primitive represents ordinary renewal, compromise response, term
narrowing and termination. Their reasons differ; the historical operation does
not. There is no interval in which old and new possession material are both
current. A future experiment could choose overlap, but it would need to make the
additional authority window explicit.

## Authority and knowledge

The recipient Porter is the only component that changes its recipient-local
standing. This implementation permits a locally trusted administrative ceremony
or already-verified claim-provider evidence to ask it to do so. Technical
Passport supplies claims; it does not mutate PORTER facts and is never consulted
for ordinary Package admission.

A Porter cannot respond to compromise it has not learned. With no unsolicited
control channel, stale exposure lasts until local ceremony or bounded expiry.
This chooses offline verification and no hidden push over instantaneous global
compromise response. Passport absence can prevent a ceremony needing fresh
claims, but cannot interrupt correspondence already decidable from local truth.

## History and custody

Exact identity-and-digest replay checks historical AC before current standing.
It repairs acceptance knowledge without creating responsibility, even after
succession or termination. Changed bytes or any new Package identity must pass
current standing.

Custody allowance belongs to the sender-recipient relationship, not an
Introduction generation. Every uncollected AC across old and new standing counts
together. Rotation therefore cannot reset resource responsibility. Narrower new
terms apply to new AC while all old AC and CL remain truthful.

## Crash reconstruction

A candidate IN without its predecessor's change fact is inert, so restart uses
old standing. Once the atomic change fact exists, restart follows it, so only its
successor (or termination) is current. Current-standing and budget files are
projections; interruption after the threshold cannot reverse it. A running
Porter also notices a separately performed local ceremony through the unique
predecessor transition slot.
