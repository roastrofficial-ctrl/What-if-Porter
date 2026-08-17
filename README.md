# PORTER

PORTER/1 is semantically frozen. Its reproducible maturation measurements,
10,000-item pressure results and accepted/rejected optimizations are documented
in [REALITY-CHECK.md](REALITY-CHECK.md); the invariant set is in
[CONFORMANCE.md](CONFORMANCE.md).

PORTER 1.1 protects the AC threshold with recipient-local standing. The protocol
shape is in [INTRODUCTIONS.md](INTRODUCTIONS.md), and its 10,000-attempt hostile
experiment is reported in [SECURITY-CHECK.md](SECURITY-CHECK.md).

PORTER 1.2 makes that standing succeedable without rewriting history. The model
is specified in [STANDING-SUCCESSION.md](STANDING-SUCCESSION.md), and the stolen
capability, race, crash, budget and real Butterfly results are in
[COMPROMISE-CHECK.md](COMPROMISE-CHECK.md).

PORTER 1.3 removes the recipient-local god-hand. [CEREMONIES.md](CEREMONIES.md)
describes separately granted, bounded Porter-recipient ceremony;
[CEREMONY-CHECK.md](CEREMONY-CHECK.md) records the delayed real compromise and
hostile measurements. HTTP's newly exposed assumptions are isolated in
[CARRIAGE-PRESSURE.md](CARRIAGE-PRESSURE.md).

Early packet networks briefly experimented with directly addressable
computational hosts. The resulting security and operational failures established
the Host Isolation Principle:

> A computational Host shall not be directly addressable through a communications network.

A Host appoints a **Porter**. Network participants deposit a **Package** with the
recipient Porter, which holds it in a local mail slot. Arrival never calls, wakes,
interrupts or executes the Host. The Host must explicitly **COLLECT**. A response
is another Package travelling in the opposite direction, called a **Return**.

## Generation I experiment

Generation I asks only whether two Dockerised Hosts with `network_mode: none`
can perform useful asynchronous correspondence through separate networked
Porters. Host–Porter IPC is a private filesystem mail slot. Porter–Porter carriage
is HTTP/JSON labelled **HOST INTEGRATION TRANSPORT**; it is scaffolding, not the
PORTER network imagined by the protocol.

```text
Sender Host (no IP)                 Recipient Host (no IP)
       │ DEPOSIT                           ▲ COLLECT
       ▼                                   │
 Sender Porter ─── HOST TRANSPORT ─── Recipient Porter
```

Run the protocol tests and strong Docker experiment:

```sh
python3 -m unittest -v
./tests/docker_generation1.sh
```

The Docker test starts both Porters and only the Sender Host. It proves the
Package is held at the recipient boundary while no Recipient Host process exists,
then starts that Host to collect and deposit a Return. Both Host containers lack
`eth0` and IP routes.

## PORTER/1

A Package is UTF-8 JSON with a small carriage-visible envelope and opaque object
payload:

```json
{
  "protocol": "PORTER/1",
  "package": "PKG-…",
  "from": "find-me",
  "to": "harmonicdb",
  "kind": "hdbe.call",
  "created": 0,
  "expires": 300,
  "reply_to": "find-me",
  "in_reply_to": "PKG-…",
  "payload": {}
}
```

`reply_to` and `in_reply_to` are optional. A successful network deposit produces
a `RECEIPT` whose state is `HELD_FOR_COLLECTION`. Acceptance is not processing.
Generation I supports `PACKAGE`, `DEPOSIT`, `COLLECT`, `RETURN`, `RECEIPT`, and
`REFUSE`. It deliberately has no Introduction, authority claim, retry guarantee,
discovery, withdrawal or remote execution primitive.

The Porter knows identities, Kind, size implied by the envelope, creation/expiry,
reply relationships and routing configuration. It does not interpret application
payloads. Host wall time, POSIX atomic rename, shared filesystems, Docker DNS and
HTTP remain explicit host dependencies.

## First Butterfly victim

HarmonicDB is the first real Host behind a Porter. Its container has
`network_mode: none`, exposes no listener, and polls its private mail slot. Find
Me now deposits opaque `hdbe.call` Packages locally and waits to collect a
`porter.return`. HDBE/1 remains the application protocol inside the payload;
PORTER does not become a database protocol.

This exposes the first pressure honestly: Laravel's model API is synchronous, so
its adapter currently waits at the collection boundary. The wire is no longer
request/response, but the application control flow still is. Generation II should
investigate durable collection tickets and application continuation after a
Return, rather than hiding longer waits inside synchronous calls.

## Generation I invariants

- A Host has no IP network interface or route.
- A Host exposes no network listener and cannot be addressed by another container.
- A Porter cannot initiate Host execution.
- Arrival changes only the Porter's held mail slot.
- A Host sees a Package only by explicitly moving it into `collected`.
- Carriage preserves unknown payloads without interpretation.
- The sender addresses a recipient identity, never a Host location.
- Returns are Packages and obey the same deposit/collection law.

## Generation II — Collection Tickets

A deposit now yields a durable local `CT-…` Collection Ticket. Lodgement ends
without waiting for processing or a Return. A later Host execution may inspect
the Ticket without collecting, explicitly collect one held Return, or abandon
the application work. Tickets and Returns survive absence and restart of both
the Host and its Porter.

The Ticket lifecycle is deliberately observational rather than magical:

- `OUTSTANDING` means no Return has yet been observed; it does not promise that
  the recipient has not computed one.
- `RETURN_HELD` means at least one matching Return is locally available.
- `COLLECTED` records the single deterministic Return selected by the successful
  collector. Repeated collection reports `ALREADY_COLLECTED`.
- simultaneous collectors use a local lock; losers report
  `COLLECTION_CONTESTED` rather than pretending exactly-once execution.
- `EXPIRED_OBSERVED` records that a Host inspected after the Package expiry. It
  does not erase a Package already in carriage or a late Return.
- `ABANDONED` ends the application intention, not the correspondence. A late
  Return remains held and becomes `ABANDONED_WITH_RETURN` evidence.

Duplicate Returns are retained as facts. PORTER deterministically collects one
and leaves the others visible; it neither suppresses them nor claims that the
recipient computed only once. PORTER owns Tickets and Package carriage. The
requesting application separately owns what should happen after collection.

Run the generations:

```sh
python3 -m unittest -v
./tests/docker_generation1.sh
./tests/docker_generation2.sh
./tests/docker_generation3.sh
```

Generation II exposed a mundane but important protocol dependency: shared IPC
lock files need an explicit cross-user permission ABI. Atomic rename alone was
not sufficient when Porter and Host containers used different users.

## Generation III — Lodgement Integrity

Generation III found a threshold. A Host privately drafts Package, Ticket and
Lodgement identities, then atomically publishes one canonical `LG-…` **LODGED**
fact into its local Porter boundary. Before publication there is no
correspondence. After publication the Porter is responsible, even when the
Ticket view, Package association and outgoing Package have not yet been
materialised.

```text
private draft
    │ atomic publication
    ▼
LODGED { Lodgement, Ticket, Package }
    ├── Collection Ticket view
    ├── Package → Ticket association
    └── outgoing Package
```

Those three lower facts are replay-safe projections. Both the Host-side client
and a restarted Porter can recover them from LODGED. The crash matrix interrupts
after publication and after every projection; every case recovers as
`DEFINITELY_LODGED`. A missing canonical fact is `NEVER_LODGED`. Local ambiguity
did not need a third state because POSIX atomic rename supplied one honest
linearisation point.

This resembles a write-ahead record, but not a database transaction: it neither
rolls back remote computation nor commits application work. A later ambiguity
still exists if a recipient Porter accepts a Package but the sender Porter dies
before retaining the Receipt. That is carriage knowledge, not local lodgement
integrity.

## ROUNDS — standard client vocabulary

ROUNDS remains absent from the PORTER/1 wire protocol, but has graduated into
the standard Host-side client vocabulary. A client can make one durable `RD-…`
Round over one or many Collection Tickets. Its `PORTER-ROUNDS/1` record says who
initiated the boundary visit, when it began and finished, and what state and
timing facts were observed for every Ticket.

A Round only observes. It never collects a Return, chooses a cadence, schedules
another execution, or advances application work. Those are explicit Host
decisions. Find Me decides that an active human journey deserves frequent
attention, asks the client to make a Round, then separately collects and advances
its own continuation ledger. The Porter never schedules, wakes or calls Find Me.

Return-held time and Host-observed time are recorded separately. The difference
is **observation latency**, not carriage latency. A crash after observation
leaves the Return collectable. A crash after collection leaves application
completion outside PORTER, although the retained collected Package permits a
later application attempt to reason about recovery.

## Generation IV — Carriage Knowledge

Generation IV separates a remote fact from the originating Porter's knowledge
of it. The recipient atomically publishes one canonical acceptance fact whose
identity is `AC-…` and which contains the accepted Package. The inbox is a
replay-safe projection of that responsibility. If the recipient restarts after
acceptance but before materialising the inbox, it reconstructs the Package.

A Receipt now attests exactly one historical fact:

> The named recipient Porter durably accepted responsibility for this exact
> Package identity and digest at the stated time.

Its state is `REMOTE_PORTER_DURABLY_ACCEPTED`. It does not attest to Host
collection, processing, success, Return lodgement, or current custody. A
successful HTTP response is merely transport until that evidence is durably
retained by the sender. Before then the sender records `ACCEPTANCE_UNKNOWN`.

Repeated carriage preserves `PKG-…`. The recipient returns the original
acceptance evidence when identity and content match; the same identity with
different content is refused. Thus repetition can repair knowledge without
multiplying correspondence. The recipient owns this identity recognition at its
acceptance boundary. It does not deduplicate application execution.

The strong experiment deliberately loses evidence after real HDBE correspondence
has been accepted, restarts the sender, repeats carriage, recovers the original
acceptance, and then continues through isolated HarmonicDB collection and an
ordinary Return. Find Me remains untouched until it makes a Round.

The historical lesson is:

> **Fact can outrun knowledge.**

## Generation V — Responsibility After Acceptance

Collection has earned its own immutable `CL-…` threshold. It can only be
initiated by the recipient Host. The fact contains the exact accepted Package,
names its `AC-…`, collector and time, and attests narrowly that the Package was
made recoverable in Host custody. It does not attest that the Host process
retained private evidence, began application work, completed work, committed an
application transaction, or lodged a Return.

Before `CL`, `AC` plus the recoverable inbox projection lets the recipient Porter
claim current custody. After `CL`, the Host can recover the Package from the
Collection fact and the Porter can no longer claim it currently holds the
correspondence. The collected Package and Package-to-Collection association are
replay-safe projections. A crash may briefly leave duplicate byte projections,
but the canonical facts assign responsibility only once and recovery repairs the
view.

Repeated collection returns the original `CL`; it repairs the Host's knowledge
or projection rather than creating a second transfer. `LG`, `AC`, and `CL`
remain immutable historical facts. Collection knowledge stays at the recipient
boundary and does not silently travel to the origin.

The strongest experiment killed networkless HarmonicDB immediately after `CL`
and before HDBE processing. Restart recovered Host custody, then separately
performed and recorded the application attempt, lodged a Return, and allowed
Find Me to collect it normally. The crash proved correspondence recovery; it did
not prove exactly-once HDBE execution.

The historical lesson is:

> **Collection transfers custody, not meaning.**

## Generation VI — Application Disposition

Generation VI attempted the smallest plausible generic `DS-…` disposition and
removed it. `PROCESSED`, `COMPLETED`, `FAILED`, and `IGNORED` each required an
application-specific definition. Contradictory Host assertions were equally
well-formed and PORTER possessed no communications evidence with which to
validate either.

The real HDBE experiment crashed after application read, after a database effect,
after HarmonicDB's result record, after Return draft, and after Return Lodgement.
The decisive case was an HDBE effect without a retained application result:
PORTER's `LG`, `AC`, and `CL` history remained complete while application reality
was fundamentally ambiguous. PORTER could neither recommend retry nor claim
success. Later application records enabled HarmonicDB's own recovery, not a new
PORTER state.

A Return contributes ordinary correspondence facts: its own `LG`, later `AC`
and `CL`, plus the preserved `in_reply_to` relationship. It does not prove that
its parent succeeded, failed, completed, or was processed at all. Absence of a
Return proves only that PORTER has no Return Lodgement.

### PORTER DOES NOT KNOW

Experiments now establish that PORTER does not know:

- whether application code began or parsing succeeded;
- whether an application effect occurred, occurred once, or committed;
- whether collected correspondence was semantically valid;
- whether application work succeeded, failed, completed, or was ignored;
- whether a Return means success, failure, progress, rejection, or nonsense.

PORTER owns correspondence integrity through recoverable Host custody.
Applications own interpretation, effects, transactions, recovery and decisions
to lodge further correspondence. No workflow state, callback, computation retry,
or disposition primitive was added.

The historical lesson is:

> **Correspondence ends where meaning begins.**

## Research horizon

No immediate PORTER Generation VII is required. The core lifecycle has reached
a stable conceptual boundary. Two longer-term Butterfly questions remain visible
but have not earned PORTER generations:

- **No Web Servers:** whether an inbound web-server fossil has any role when
  application Hosts never accept unsolicited network communication.
- **Continuous Correspondence:** whether durable ordered Segments can give
  correspondence duration without reintroducing a Host-to-Host connection.

Neither is implemented here.

ROUNDS has earned shared names and an observable client journal, but not a
PORTER wire verb. Hosts can therefore share the boundary ceremony while retaining
genuinely different attention and continuation policies.
