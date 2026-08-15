# PORTER — Generation I: The Host Stays Inside

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

## Candidate Generation II — Collection Tickets

The most interesting next mutation is not authentication yet. It is admitting
that useful Hosts should not block while staring at their Porter. A deposit could
yield a durable local Collection Ticket; a Host could continue other work and
later ask which tickets have Returns. This would force idempotency, duplicate
collection, expiry and crash recovery to emerge before Introductions and Passport
claims are layered onto an unstable primitive.
