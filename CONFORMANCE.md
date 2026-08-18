# PORTER/1 Conformance

PORTER 1.0 freezes the correspondence semantics earned by Generations I–VI.
Performance work is conformant only while every statement below remains true.

## PORTER 1.5 rendezvous continuity

- Static rendezvous configuration establishes only local generation-zero knowledge.
- Later location and carriage-key knowledge is an immutable signed `RV` chain.
- Carriage keys, DNS names, ports and endpoint possession are not Porter identity.
- Transition authority is separate from standing and operational carriage keys.
- Current knowledge advances only through one exact predecessor generation.
- Replay cannot move current knowledge backwards.
- Out-of-order hostile evidence creates no pending durable queue.
- Valid authority conflict suspends carriage instead of choosing by arrival time.
- Expiry leaves identity, standing and correspondence history intact.
- A stale failure claims only failure of the locally known approach.
- An unchanged spooled Package retries after authenticated knowledge improves.
- Movement mutates no `LG`, `IN`, `SC`, `AC`, `CL`, `CM` or application identity.
- Ordinary carriage needs no live continuity authority, Passport, or central oracle.

## Isolation

- A computational Host has no IP connectivity, listener, or remotely addressable
  endpoint.
- Arrival, acceptance and held correspondence cannot execute, wake, notify or
  call a Host.
- Only a Host may initiate inspection, ROUNDS and Collection at its local Porter
  boundary.
- A Porter cannot initiate Host IPC.

## Thresholds and evidence

- `LG-…` is the sole threshold between private Host draft and lodged
  correspondence.
- `AC-…` is the sole threshold at which a recipient Porter accepts durable
  responsibility for one exact Package identity and digest.
- `CL-…` is the sole threshold at which an accepted Package becomes recoverable
  in recipient Host custody.
- Canonical `LG`, `AC` and `CL` facts are immutable. Tickets, associations,
  outgoing, inbox and collected files are recoverable projections.
- `IN-…` records immutable historical establishment. A `PORTER-STANDING/1`
  standing-change fact may select its successor or terminate current standing;
  neither operation rewrites the Introduction or any historical AC.
- Outstanding count and byte allowance belong to the sender-recipient
  relationship and remain continuous across every standing generation.
- Operational Introduction authority cannot authorize a ceremony that changes
  itself. Ceremony requires a distinct immutable recipient-local `CG-…` grant
  whose relationship, terms, expiry, pending evidence and change count are
  bounded.
- `CM-…` is durable Porter-directed security evidence, not Host correspondence.
  It creates no ordinary AC or CL, cannot wake a Host, and can cause standing to
  change only when the recipient Porter locally publishes SC.
- Recipient ceremony replay and reordering cannot fork or reverse the immutable
  standing chain. The origin may claim an applied ceremony only after retaining
  its result.
- Native carriage addresses stable Porter identities through replaceable local
  rendezvous knowledge. Location and connection lifetime do not mutate Package,
  Introduction, standing, acceptance or custody history.
- A complete native frame is mutually authenticated, confidential, integrity
  protected and bound to its sender, recipient, Unit identity and Unit class.
- Package/Ceremony movement and evidence return are independent native Units.
  Transport completion never establishes remote-acceptance or ceremony-result
  knowledge; only durable returned evidence does.
- Transport completion is not PORTER knowledge. The origin may claim remote
  acceptance only after retaining valid acceptance evidence durably.
- Package identity remains stable through retry and recovery. Repeated evidence
  for one identity does not create another correspondence fact.

## Observation and meaning

- A Round is an explicit Host visit to its own boundary. Cadence and attention
  remain Host policy.
- Observation latency is distinct from carriage latency and Collection cost.
- Collection transfers recoverable custody, not application meaning.
- PORTER has no Application Disposition and makes no claim about parsing,
  processing, effects, transaction commit, completion, failure or exactly-once
  execution.
- A Return is ordinary correspondence with a preserved `in_reply_to`
  relationship; PORTER does not interpret its meaning.
- Application continuation and recovery remain application-owned.

The executable targets are `tests/conformance_1_0.sh`, `tests/security_1_1.sh`,
`tests/security_1_2.sh` and `tests/security_1_3.sh`. Their isolated modes must
remain green before and after every optimisation. Native-carriage conformance is
`tests/security_1_4.sh`.
