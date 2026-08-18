# PORTER Public House

This is a self-contained native-carriage demonstration. A networkless Visitor
Host lodges an order with its Porter. A separate networkless Taproom Host must
explicitly collect it, serves a pint, and lodges a Return. Only the two Porters
join the carriage network.

From the PORTER repository root, run:

```sh
./demo/run.sh
```

The command builds the four small containers, performs one complete journey,
prints its durable Package, Lodgement, Collection Ticket, Acceptance and
Collection identities, then removes the containers and demo volumes.

The keys embedded in `compose.yaml` are public laboratory fixtures. They prove
identity binding and wire protection, but are intentionally unsuitable for any
deployment beyond this disposable demonstration.

## What the demo does not pretend

- Host arrival is not an HTTP request and does not invoke the Taproom Host.
- Acceptance is not service completion; the Host explicitly collects.
- A response is not returned on the request connection. It is another Package.
- Docker DNS and the two ports are replaceable rendezvous knowledge, not Porter
  identities.
