# PORTER/1 Conformance

PORTER 1.0 freezes the correspondence semantics earned by Generations I–VI.
Performance work is conformant only while every statement below remains true.

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

The executable targets are `tests/conformance_1_0.sh`, `tests/security_1_1.sh`
and `tests/security_1_2.sh`. Their isolated modes must remain green before and
after every optimisation.
