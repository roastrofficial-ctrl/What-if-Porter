# PORTER-ATTESTATION/1 — First check

Measured 24 August 2026. This check asks two different questions which the
proposal initially joins together:

1. can a nonce-bound, expiring environmental statement be signed and checked;
2. does that statement prove a Host is non-addressable to a remote depositor?

The first is implemented for Level 0. The second is **not proven at Level 0**.
A self-attestation proves that the holder of the configured measurement key
signed particular bytes. It proves the network state only to somebody who
already trusts that process, its observation code, its key custody and the
kernel view supplied to it. This is useful misconfiguration evidence, not an
independent proof of isolation.

## Reproduction

```sh
./tests/docker_attestation.sh
```

The isolated and ordinary Docker observations were respectively:

```json
{"active_interfaces": [], "default_routes": [], "external_routes": [], "tcp_listeners": []}
{"active_interfaces": ["eth0"], "default_routes": ["eth0:0.0.0.0/0.0.0.0"], "external_routes": ["eth0:0.0.0.0/0.0.0.0", "eth0:172.17.0.0/255.255.0.0"], "tcp_listeners": []}
```

Five focused tests establish signature and content integrity, expected-root and
expected-nonce binding, expiry, ordinary Package encapsulation, Linux snapshot
parsing, and the counterexamples below.

## What survived

- An Ed25519-signed immutable AT identity can bind host, challenge, observation,
  expiry, measurement root and raw evidence without Porter interpretation.
- Exact nonce matching defeats replay into a different challenge; explicit
  expiry gives the verifier a local freshness decision.
- `network_mode: none` produced the expected empirical snapshot: no non-loopback
  active interface, IPv4/IPv6 external route or TCP listener.
- The AT object fits unchanged inside the opaque payload of an ordinary
  `porter.attestation` Package. No daemon branch or control-plane message was
  added.

## What did not survive

**No listeners is not necessary for non-addressability.** A process listening
only on `127.0.0.1` makes `no_listeners` false while remaining unaddressable from
outside its namespace. The test constructs exactly this state. Listener absence
may be a stricter Host policy, but it is not the claimed network property.

**No default route is not sufficient for non-addressability.** A directly
connected or specific non-default route permits addressing without a default
route. The test constructs an active `eth0` and specific route while
`no_default_route` remains true. The prototype therefore adds signed
`no_active_interface`, `no_external_routes`, and the raw lists from which every
boolean is derived.

**A signature chain does not by itself make observation independent.** Level 0
is an authenticated assertion by the Host. Level 1 can authenticate what an
orchestrator deployed, but a definition such as `network_mode: none` is not a
fresh measurement of all runtime namespace state. A useful Level 1 issuer must
inspect the running container identity and namespace, bind both to the deployed
definition, and sign the resulting observation from outside that namespace.

**A TPM quote does not automatically quote network-namespace state.** Ordinary
PCR quotes authenticate measured boot/configuration values. Level 2 needs a
specified measured agent, key-release policy and kernel/orchestrator measurement
path that binds the live namespace observation to quoted state. Without that
construction, “TPM quote of the running network-namespace state” names an
assurance goal, not an implementation.

## Protocol correction

The pictured “Porter forwards challenge to attestation agent” would give an
incoming Package causal power over Host-side execution and would require Porter
to recognize AT traffic. Both conflict with the existing boundary. The clean
flow is:

```text
challenger lodges ordinary challenge Package
  → recipient Porter holds it opaquely
  → Host chooses a later Round/attention opportunity
  → narrow Host adapter collects and measures
  → Host lodges ordinary AT Return
```

The challenge may be requested before a first application deposit, but it may
not force immediate Host execution. That preserves Host initiation, ordinary
carriage and payload opacity at the price of Round-bounded attestation latency.

## Implementation boundary

`porter.attestation` is an experimental Level 0 primitive, not daemon policy. It
issues and verifies a canonical signed fact, rejects contradictory signed
claims, measures Linux `/proc/net` routes/listeners and `/sys/class/net`
interfaces, and supplies a CLI. It intentionally does not add key provisioning,
automatic cadence, quarantine, Level 1 Docker-socket access, or a Level 2 label.
Those would falsely imply assurance the experiment has not earned.

## Verdict

The narrow hypothesis is **partly supported**: PORTER can carry a fresh,
nonce-bound, independently signature-verifiable environmental assertion without
interpreting it. The large claim is **disproved for Level 0 and not yet proved
for Levels 1–2**: the current signature establishes who asserted the snapshot,
not that the snapshot is true independently of the Host. The Docker experiment
supports the concrete `network_mode: none` configuration, while the two
counterexamples require the attested predicate and assurance language to be
tightened before AT can be called proof of non-addressability.
