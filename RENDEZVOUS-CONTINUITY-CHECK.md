# PORTER 1.5 — Continuity Reality Check

## Model and hostile results

The experiment tested location-only, key-only, combined, overlap, no-overlap,
future activation, attempted cancellation, expiry, restart, authentic replay,
wrong predecessor, out-of-order delivery, forged signatures, endpoint takeover,
substitution, oversize, and valid authority conflict.

- Control of DNS, a port, the old endpoint, or K1 cannot sign a transition.
- Out-of-order evidence creates no pending fact; replay after its predecessor
  advances normally.
- Old authentic evidence remains history and cannot move current backwards.
- Valid equivocation suspends carriage rather than choosing by arrival time.
- Crash after the immutable fact or projection reconstructs from facts.
- Expiry removes an approach, not identity or history.
- Existing Package identity and Lodgement survive stale reachability.

The mixed 10,000-attempt benchmark contained random identities, invalid
signatures, substitution, oversized evidence, and authentic historical replays.
Eight thousand claims were refused; 2,000 authentic replays were idempotent. It
took 421.43 ms wall / 421.35 ms CPU, maximum RSS was 30,797,824 bytes, and it
created zero files and zero bytes.

## Cost

| Operation | Result |
|---|---:|
| static dictionary lookup, median | 83 ns |
| authenticated retained lookup, median | 750 ns |
| authenticated retained lookup, p95 | 1,625 ns |
| sign 538-byte movement evidence | 0.910 ms |
| verify and publish durable transition | 2.807 ms |

Authenticated knowledge adds about 0.67 microseconds to ordinary route
selection. Movement verification is exceptional work, not per-Package crypto.
Raw results are in `benchmarks/results/porter-1.5-continuity.json`.

## Real Butterfly movement

Unchanged Find Me first completed real `HDBE/1 info` as
`PKG-571cdbe03e1444658288b0e5be31df3b`, collecting Return
`PKG-ab7465543e3b4b4d9afbaedc5fa030ba` as
`CL-a6fcf404db0f4f4a8fa84485563a9a0c`.

HarmonicDB signed `RV-9df4644225f1f592efe36fced5b772ca`, changing
`porter-harmonicdb:9177`/K1 to the unrelated Docker name
`weird-new-container-thing:9288`/K2. Find Me learned it natively before movement.
With both Porters stopped, a networkless Host lodged
`PKG-ed01844759ac4310a4fcc981c407341b`. The old endpoint disappeared; the same
Package reached B/K2, real HDBE succeeded, and Return
`PKG-a0aaca9441e6436593bb5b23e88e39c7` was collected as
`CL-04afb29341cc40be9537f74054050d96`.

The seven pre-movement HarmonicDB `IN`/`SC` files retained byte digest
`90b8579c797174296e3024222484354a35abeafc570425784845039a6a902837`.
Port 9177 closed. No Host or application configuration changed.

Protected Ceremony `CM-b801eef2701c4481811d58342c091b75` then published
`SC-d4ad27ca07ba4b4285ce0454ae237eaa`; its result returned independently.
Generation 2 became current, and authentic generation-1 replay left it current.

## Missed evidence

Find Me was absent while HarmonicDB announced another location/key and the old
endpoint disappeared. Its already-lodged Unit retained the exact Package and
recorded `KNOWN_RENDEZVOUS_ATTEMPT_FAILED` against stale local knowledge. The
new Porter independently delivered signed evidence; no map or application was
edited.

That first run exposed an independent restart defect: unordered historical
Ceremony-result replay could rewind the origin's outbound standing projection.
The Package was honestly refused and retained as history. Recovery now applies
a result only when its predecessor is current; later knowledge cannot be
overwritten by directory order. A regression test fixes the discovered defect.

The clean repetition moved to generation 4 at port 9499/K4. Find Me initially
knew only dead generation 3 and retained unchanged
`PKG-35fe514f2cf04f5f97bc5e4cffc8bafb` under
`LG-c8dd9d6fe5c1463aa08b2b4df7d478c0`. After signed evidence arrived, the same
Package completed real HDBE. Return `PKG-596414b050104b8ba47821a82135ef4f`
was collected as `CL-a9e31fcca7e64f0d9623316cd8d27bd0`.

HarmonicDB remained `network_mode: none`; HTTP carriage remained absent. Docker
DNS and ports survive only as replaceable location plumbing inside an `RV`.
Technical Passport was not consulted for steady-state carriage or movement.

## Pressure record

Stable identity is the locally established Porter name plus retained continuity
root and chain—not a socket or operational key. A carriage key is current proof
for protected transport. An `RV` is local authenticated knowledge of how to
attempt that identity. The separate continuity authority may change it; peers
learn through signed native evidence.

Missed evidence waits in the spool until verifiable evidence arrives. No-overlap
location and key changes work if the peer retained the root and the mover still
knows how to approach that peer. A stale failure says only that one approach did
not connect. Conflicts suspend choice; out-of-order claims require bounded
replay; expiry leaves identity and history intact.

The costliest surviving attack is a correctly shaped invalid Ed25519 claim, but
the mixed 10,000 run created no growth. Unexpectedly elegant: evidence can
travel after its operational key dies because authority lives in the retained
chain, not its connection. Unexpectedly difficult: historical recovery order in
an adjacent Ceremony projection.

The earned historical lesson is:

> A route may expire and an operational key may die. A Porter remains itself
> only where continuity can be proven from authority retained before the loss.

## Exactly one next experiment

Run **NO WEB SERVERS**: inventory each remaining conventional listener, identify
the historical problem it solves, and test whether native Porter carriage plus
Host isolation can replace it without smuggling synchronous invocation back
into the model.
