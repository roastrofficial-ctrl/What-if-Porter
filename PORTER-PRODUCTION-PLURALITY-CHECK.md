# PORTER production plurality — hostile custody check

Measured 26 August 2026. This experiment promoted the previously earned
recipient/custodian identity split into production Package fan-out, then attacked
it as infrastructure for a high-value networkless signing Host.

## Verdict

**Production plurality improves availability and incident attribution, but does
not turn custodian testimony into truth. It needs no trusted coordination layer
for Package carriage.**

One immutable Package was placed into independently retryable native Units for
three custodians. One provider was wholly absent. A second authenticated as the
right custodian, claimed durable acceptance, and retained nothing. A third
actually accepted. A fourth was introduced later and accepted the same Package.
Every original provider was then removed, yet the unchanged Host recovered the
old correspondence and new correspondence through the replacement provider.

This is useful ordinary replication with Porter-native custody boundaries. It is
not quorum, Byzantine consensus, proof of storage, or global Host availability.
No new grand abstraction was earned.

## Reproduction

```sh
./tests/docker_production_plurality.sh

# The complete suite was also run. Frozen Docker status is recorded below.
python3 -m unittest -v
for generation in 1 2 3 4 5 6; do
  ./tests/docker_generation${generation}.sh
done
```

The focused experiment uses real authenticated and encrypted loopback TCP while
the Docker container itself has `--network none`.

The resulting PORTER suite passed **200/200** cases. Frozen Docker Generations
I–III passed. Generations IV and V reached normal Package acceptance, then the
separate HarmonicDB Host image exited without creating its expected Collection
fact; a clean committed PORTER baseline failed Generation V at the identical
assertion. Generation VI's external Host remained running instead of reaching
its configured first crash point, so that run was stopped rather than waiting
through every 120-second case. Those external-fixture journeys are recorded as
blocked, not passed and not attributed to plurality. The production plurality
path does not run in those HTTP-only generation configurations.

## Production shape

Depositor-local selection may now name several custodians:

```json
{"signing-host":["provider-a","provider-b","provider-c"]}
```

Staging one Package creates one native Unit per selected custodian. The Package
bytes and identity are shared; Unit identity, destination, attempts, settlement
and retained evidence are custodian-indexed. A response settles only the Unit
whose authenticated peer returned it. A success or refusal cannot erase a
sibling attempt.

No custodian receives the selection list, knows of siblings, elects a leader or
updates replica state. The Package contains only its logical sender and recipient.
Adding `provider-d` queues a new physical attempt for the already immutable
Package. Retiring a local attempt records only:

```text
DEPOSITOR_STOPPED_THIS_PHYSICAL_CARRIAGE_ATTEMPT
```

It does not claim that the provider failed, forgot custody, or agreed to stop.

## The dishonest acceptance attack

The malicious provider used its legitimate native private key and returned a
perfectly coherent receipt: correct Package identity, recipient, digest and
acceptance vocabulary. It had no local store at all.

PORTER retained that as evidence attributed to the authenticated custodian. That
is correct and limited: the sender knows that B made an acceptance claim. Native
channel authentication cannot prove that B performed durable I/O or still
possesses the bytes. Even a portable signed AC would remain testimony about a
historical act, not present possession.

Therefore plurality tolerates this liar for availability only because C or D
really retains a recoverable copy. It does not identify the lie without a later
challenge, external audit, or failed recovery. M-of-N signed claims would not
repair this semantic limit; they would count testimony.

## Total infrastructure replacement

The test introduced D after the original deposit, obtained separate evidence for
C and D, stopped retrying vanished A, and removed C's entire custody root. B had
never stored the Package. Selection then contained only D.

The networkless Host collected the pre-migration Package from D using the
ordinary Host Runtime and later collected a newly deposited Package from D. It
saw neither custodian identity nor topology. Restart preserved the original B,
C and D-attributed evidence and A's explicit retired-attempt record byte for
byte. No canonical Host-to-Porter mapping existed.

## Real-World Pressure Ledger

### Security

Plurality removes a single custodian's ability to destroy availability or hide
all correspondence. It does not remove the depositor's selection/configuration
authority, compromise of every chosen custodian, or false acceptance testimony.
Each additional endpoint and key expands attack surface. Exact Package/digest
and authenticated-origin correlation prevents one custodian settling another's
Unit, but cannot inspect remote durability.

### Availability

The result is genuine under independent failures: A may disappear and B may lie
while C or D still permits recovery. Availability is at least one reachable,
honest, retaining custodian—not M claims. Fan-out is currently retried serially
by one native tick loop, so a sufficiently slow endpoint can impose latency even
though its failure cannot settle siblings. Parallel scheduling remains
operational work.

### Trust

There is no new trusted coordinator and no custodian quorum. The depositor trusts
its local selection and rendezvous knowledge; the Host trusts whichever local
custody boundary it chooses to inspect. The current Standing proof is logical-
recipient scoped and reused across selected custodians. Native peer
authentication prevents one custodian using that proof while impersonating the
depositor's custodian, but deployments must still treat wider verifier exposure
as a key-management cost.

### Privacy

Every custodian that receives the Package learns its correspondence metadata and
clear payload after native decryption. Plurality therefore multiplies disclosure
roughly with the number of actual recipients. A dead endpoint learns nothing;
that is not a privacy design. Payload-level end-to-end encryption is outside this
experiment.

### Operations

Operators gain explicit per-custodian outstanding Units, evidence and retirement
records. They must also manage more keys, rendezvous histories, capacity and
stale attempts. Custodians require no sibling configuration. Host access to a
replacement local custody root remains deployment plumbing, not correspondence
topology.

The production seam that failed to pluralize is Standing ceremony. Ceremony
routing intentionally still chooses the first custodian. A relationship
succession therefore cannot yet be driven coherently across independently
operated custodians by this implementation. Adding hidden sibling coordination
would violate the result. Production deployment needs custodian-indexed ceremony
attempts/results or independently managed recipient-local Standing before this
can be called complete plural operation.

### Performance

The unavoidable tax is linear: N selected custodians create N encrypted Units,
N transmissions, up to N remote durable copies and N evidence records. The
hostile four-provider focused journey completed in under one second locally, but
that is a conformance observation, not a capacity claim. No batching,
parallelism, repair policy or storage compaction was earned here.

### Migration

Complete infrastructure replacement worked without changing Host identity,
Package addressing, Package bytes, Host Runtime behavior, or requiring
custodians to coordinate. Depositors may possess different local selections; no
canonical global map is required. Outstanding attempts do require an explicit
local decision to retry, extend or retire them.

### Evidence

The depositor retains which authenticated custodian returned each acceptance or
refusal, which Unit it answered, and which local attempts were retired. Canonical
AC remains recipient-local and the first ordinary receipt remains compatible
with earlier PORTER generations; additional custodian receipts are separately
indexed. Native attribution is local channel evidence, not a portable signature.
After an incident it proves received claims and local actions, not remote disk
truth, current possession, Host intent, application processing or global
availability.

## Foundational invariant

The following is now frozen in `CONFORMANCE.md`:

> **Hosts have no network presence. Custodians do. A Porter speaks only for the
> custody and carriage facts it actually establishes; it never represents Host
> identity, intent, application state or global availability.**

Plural production carriage supports that invariant. The network contains
parties presently selected and authorized to hold correspondence for a Host; it
does not contain the Host or a singular infrastructure object that is the Host.

## Stop condition

This experiment stops here rather than inventing a roster, logical deposit,
quorum or repair controller. The useful result is plural independent custody
with attributable attempts. The exposed next pressure is equally concrete:
plural Standing lifecycle and operational scheduling. Neither requires changing
Package identity, and neither has yet earned a new protocol abstraction.
