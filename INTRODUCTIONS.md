# PORTER Introductions/1

An Introduction is durable recipient-local standing. It answers only:

> May this correspondent ask this Porter to cross AC under these terms?

It does not authenticate an application, interpret payload meaning, create Host
work, or assert that a future Package has been accepted.

## Boundary

An authority adapter verifies first-contact evidence and returns a normalized
`subject` and `issuer`. Technical Passport can do this offline using its signed
Authority, credential and revocation material. PORTER then applies local terms;
the claim provider never chooses Kinds, size or custody allowance.

Successful establishment publishes one immutable `IN-…` fact containing sender,
recipient, issuer and terms. The carriage capability is stored separately with
mode `0600`. Existing standing therefore survives both Porter restart and claim
provider absence.

The experiment uses HMAC-SHA256 carriage capabilities. This is explicit
scaffolding: it proves that standing plus Package-bound possession prevents
identity-string spoofing. PORTER 1.2 adds local standing succession after theft;
secure capability delivery and federation remain unsolved.

## Admission ordering

```text
wire-size ceiling
  → Package envelope
  → exact historical AC replay
  → Introduction lookup
  → Kind / Package size / expiry
  → Package-bound carriage proof
  → outstanding count + byte allowance
  → AC
```

The proof covers the canonical Package digest, which covers identity, sender,
recipient, Kind, expiry and payload. Exact replay of an existing AC returns the
same evidence even after Introduction expiry because it creates no new custody.
Different bytes under that identity remain an error.

Custody allowance combines Package count and canonical Package bytes. Count
protects the two-inode-per-acceptance pressure found in 1.0; bytes prevents a few
large Packages consuming the same allowance. Collection releases responsibility.

The live counter is a recoverable projection. It is periodically published as a
constant-size diagnostic and reconstructed from AC/CL after restart. Reaching an
allowance triggers reconciliation with canonical history before refusal.

## REFUSE

`POLICY_REFUSED_BEFORE_ACCEPTANCE` means the recipient Porter declined to assume
responsibility. It means neither transport absence nor application rejection.
The recipient creates no AC, inbox projection or per-attempt refusal log. The
sender may durably retain returned refusal evidence against its own Lodgement.

Standing failures deliberately expose only `CORRESPONDENCE_NOT_ADMITTED` to the
stranger. The private distinctions—unknown correspondent, invalid proof, Kind,
expiry and allowance—remain process-local in this experiment. Invalid envelope
responses still reveal protocol grammar; that residual privacy trade-off is
recorded rather than silently homogenized.

## Reproduction

```sh
./tests/security_1_1.sh
./benchmarks/docker_reality_check.sh --adversarial \
  --attempts 10000 --samples 200 --quiet \
  --output /results/porter-1.1-final.json
```
