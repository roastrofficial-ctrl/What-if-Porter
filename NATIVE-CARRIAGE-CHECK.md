# PORTER 1.4 — Native Carriage Reality Check

The tested Find Me ↔ HarmonicDB Porter path now has no HTTP carriage, URL,
HTTP status, port 7070 listener or synchronous response channel. It uses framed,
mutually authenticated, encrypted TCP Units. Hosts and application packages were
unchanged.

## Failure and hostile-network results

- outgoing Package and CM Units survive recipient absence and sender restart;
- truncated header/body, bad magic, unknown version, invalid/oversized declared
  length, excess body, wrong recipient and altered ciphertext create no durable
  recipient state;
- incomplete connections are bounded to 32 concurrent readers with deadlines;
- stable sender authentication prevents a stranger from forging returned AC or
  ceremony-result evidence merely because the recipient public key is public;
- partial connection failure before a complete frame creates no fact;
- AC may exist while its evidence Unit is unable to return; exact Package retry
  recovers the same AC and origin knowledge;
- recipient restart and endpoint movement preserve all canonical history;
- ceremony and Package outer classes reach different recipient lifecycles and
  no ceremony creates Host CL.

No generic received-Unit fact is retained before semantic admission. An early
prototype did so and was rejected because authenticated-but-unauthorized traffic
could have recreated the inode attack before AC.

## HTTP comparison

Loopback Docker, 100 accepted Packages:

| Carriage | median | p95 | p99 | representative encoded bytes |
|---|---:|---:|---:|---:|
| HTTP/JSON body + synchronous evidence | 2.220 ms | 2.852 ms | 4.736 ms | 431 body bytes |
| native protected Package + separate evidence | 10.990 ms | 18.207 ms | 34.046 ms | 798 frame bytes |

Native carriage is roughly five times slower in this unoptimised experiment and
created 402 files / 189,785 bytes versus HTTP's 201 files / 64,285 bytes. It
performed 1,898 fsyncs versus 400. The cost is mainly durable two-direction Unit
machinery, fixed retry cadence and projection churn—not cryptography.

For a 561-byte ceremony-shaped plaintext, sealing cost 0.077 ms median, opening
0.104 ms, and the protected frame was 936 bytes. Ten thousand altered protected
frames were rejected in 858.19 ms. Process maximum RSS was 37,482,496 bytes.
Hostile framing and slow-connection tests created zero PORTER facts.

HTTP genuinely provided excellent framing, body limits and efficient response
carriage. Its actively harmful concept was not TCP or even a listener: it was
making remote evidence look like the return value of the same operation. Native
carriage made evidence a separate journey and thereby represented Generation IV
without simulated response loss.

## Real relocation

At rendezvous A, HarmonicDB Porter listened at port 7411. Unchanged Find Me code
lodged `PKG-4c11e392a6d58dc78dda2e03caed6325`; native acceptance evidence named
`AC-a7e7762db5b040089a292915f88d4af9`. Networkless HarmonicDB collected it,
performed real audio growth as `HDB:00000006`, lodged Return
`PKG-34ae9b3bffb54fcab03c31f5902ae141`, and Find Me collected it as
`CL-59c796cc7b78819262b98ff1a19b40e0`.

Only rendezvous knowledge then moved HarmonicDB Porter to port 9177. Port 7411
closed. The five immutable IN/SC files remained byte-identical with digest
`8cddf308fd0fa7d5a8a6febb75904aa536174bb91bb9ccb070f887c77a6f1658`.
Package addressing, cryptographic identity, standing, Hosts and application
configuration did not change.

At rendezvous B, unchanged Find Me code lodged
`PKG-962fe4686e7aa330763dced0546d0238`; native evidence named
`AC-181532a34f2348eda191e9f3876a262a`. HarmonicDB completed
`HDB:00000007`, returned `PKG-5755ae390c6246da97682b1989dcdc00`, and Find Me
collected it as `CL-118e6e3db1d2cdc7e176187e1853abed`.

## Real protected ceremony

`CM-0457dca38c264047885addbbd3b503ad` travelled as a 1,489-byte protected
native Unit at rendezvous B. The observed frame did not contain replacement
possession material; its digest was
`sha256:77e4297e568284833a7966b2f9684ef0208cba34bb5829dad42d1fdeace50534`.
Wrong recipient identity, wrong peer key and any ciphertext mutation fail AEAD
authentication.

HarmonicDB locally published `SC-2c58bf38dd6b4a7baa89d7a7f58bcbe3`, selecting
`IN-f2556dca32844a419a2df0b76bef5b8f`. Its result returned as an independent
native Unit. A subsequent attacker holding both the old operational capability
and Find Me's carriage identity was refused before AC; refusal evidence returned
natively. Replacement standing then completed real HDBE health correspondence
and Find Me collected Return `PKG-5dfed980992c4c9abb758fff9195ea3d` as
`CL-b2ce1a61466d45ec968b275abe96a5aa`.

HarmonicDB remained `network_mode: none`. Both Porter images declare no HTTP
port, port 7070 is closed, and the migrated service commands contain no route URL
or HTTP listener. There is no fallback.

## Pressure record

A Porter identity became a stable service-bound cryptographic network
principal. A rendezvous became replaceable local knowledge describing where and
under which public key that identity is currently approachable. The current map
still uses Docker DNS and a port as lower-level location, but neither appears in
correspondence or Host configuration. Stable ports did not survive; DNS survived
only as transport implementation.

Connections became disposable byte-moving incidents. Acceptance evidence
naturally became independent carriage. Store-and-forward emerged at each Porter
spool without requiring both sides to be simultaneously available.

The unexpectedly elegant result was eliminating acknowledgement recursion:
returned evidence need not itself be acknowledged because exact original replay
regenerates it. The unexpectedly difficult result was authenticating returned
evidence. Recipient encryption alone was insufficient; stable sender identity
had to bind the frame too.

The earned historical lesson is:

> A network location tells carriage where to try. Only a Porter identity tells
> correspondence whom the journey is for, and only returned durable evidence
> tells the origin what became true there.

## Exactly one next maturation experiment

Run **Rendezvous Knowledge and Identity Continuity**: discover how authenticated
location and Porter-key changes travel without static configuration, DNS-as-
identity, a central discovery oracle or rewriting correspondence standing.
