# PORTER-ATTESTATION/1

## Motivation

Non-addressability has, until now, been an architectural assertion: a
Dockerized Host with `network_mode: none`, no `eth0`, no route. That is true
inside the demonstration, but no depositor or rented Porter outside the
deployment has any way to verify it — they simply trust the operator's word.
ATTESTATION turns "this Host cannot be addressed" into a signed, checkable
fact rather than a claim in a README.

## Scope

Applies to a Host's relationship with its own local Porter. It does not
attest to correctness of application behavior, and it does not attest to
anything about the wider network — only to environmental non-addressability
at a stated time.

## The attestation fact

An `AT-…` fact is signed by a local measurement root and contains: absence of
listening sockets, absence of a default route or active interface, a
timestamp, and a nonce supplied by the challenger to prevent replay.

```
{
  "attestation": "AT-…",
  "host": "…",
  "no_listeners": true,
  "no_default_route": true,
  "observed_at": 0,
  "nonce": "…",
  "measurement_root": "…",
  "signature": "…"
}
```

## Verification flow

```
Depositor / rented Porter
    │ issues nonce
    ▼
Local Porter ── forwards challenge ──▶ Host attestation agent
    ▲                                        │ produces AT bound to nonce
    │◀─────────── AT fact (ordinary carriage) ┘
Depositor verifies signature chain
```

The challenge never executes Host application code and the Porter never
initiates it — this mirrors "a Porter cannot initiate Host execution." The
attestation agent is a narrow, purpose-built process, not the application
itself, and the resulting AT fact travels back as ordinary correspondence,
not as a control-plane message.

## Levels of assurance

- **Level 0 — self-attested.** A signed policy snapshot (e.g. read local
  interface/socket state, sign with the Host's own key). Cheap; catches
  misconfiguration; trusts the Host's own honesty.
- **Level 1 — orchestrator-attested.** The container runtime or orchestrator
  confirms `network_mode: none` at the definition it actually deployed.
  Medium assurance; trusts the orchestrator.
- **Level 2 — hardware-rooted.** A TPM quote or enclave measurement of the
  running network-namespace state. Strong assurance; trusts the silicon
  vendor's root of trust.

Deployments can mix levels; a rented tier might require at least Level 1
before accepting a Roster member (see PORTER-THRESHOLD/1), while a hobbyist
local deployment might only ever produce Level 0.

## Cadence

Attestation is periodic and pull-based, matching ROUNDS discipline — it is
not continuous surveillance of the Host. Every AT fact carries an explicit
expiry; a stale attestation is evidence of absence of proof, not evidence of
compromise.

## Revocation and drift

If the Host's configuration changes — an interface is added, a listener
opens — the next attestation attempt either fails or honestly reports the new
state. This is deliberately undramatic: ATTESTATION does not alarm or
auto-quarantine anything. It only declines to reissue a fresh AT fact
claiming an isolation property that no longer holds.

## What ATTESTATION does not know

- Whether the isolation, even if genuinely proven, is sufficient for a given
  depositor's risk model.
- The intent behind a configuration change — a deliberate reconfiguration and
  a compromise look identical from outside.
- How to detect an attacker with physical or hypervisor-level control capable
  of forging the attestation chain itself. ATTESTATION raises the bar to that
  level; it does not claim to defeat it.

## Invariants

- Attestation is carried as an ordinary Package/Return, never a side-channel
  control message.
- The Porter never interprets or acts on AT content — only the depositor and
  the Host's own operator do, matching "the Porter does not interpret
  application payloads."
- AT facts are immutable, timestamped, nonce-bound, and independently
  verifiable without trusting the issuing Porter.

## Historical lesson

> Isolation you must be told about is a policy. Isolation you can verify is a
> property.

## Relationship to THRESHOLD

An AT fact can itself be one of the artifacts fanned out and reconciled
across a Roster, so that no single rented Porter can suppress or forge
attestation freshness unnoticed by the others.

## Open questions

- Choice of hardware root of trust across heterogeneous consumer and rented
  deployments, where Level 2 may not be available.
- Whether attestation cadence should be Host-policy-driven only, matching
  ROUNDS, or whether a depositor should be able to request one before an
  initial deposit.
