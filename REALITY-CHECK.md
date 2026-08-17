# PORTER 1.0 — Reality Check

Measured 17 August 2026. PORTER/1 semantics are frozen in
[`CONFORMANCE.md`](CONFORMANCE.md). Raw results live in `benchmarks/results/`;
`porter-1.0-final.json` is the final isolated Docker run (100 samples and scales
1, 10, 100, 1,000 and 10,000).

## Reproduction

```sh
./tests/conformance_1_0.sh
python3 benchmarks/reality_check.py --samples 100 --max-scale 10000
./benchmarks/docker_reality_check.sh --profile porter-1.0-final \
  --samples 100 --max-scale 10000 --quiet \
  --output /results/porter-1.0-final.json
```

Set `PORTER_CONFORMANCE_DOCKER=1` on the conformance command to include all six
isolated-Host proofs. The benchmark container has `--network none`.

## Final baseline

The Docker filesystem produced the reproducible reference numbers below. Host
APFS was materially slower at durability barriers; its calibration is retained
as `baseline-calibration.json` rather than mixed into these distributions.

| Operation | median | p95 | p99 |
|---|---:|---:|---:|
| LG + Ticket + outgoing projection | 1.687 ms | 6.837 ms | 11.091 ms |
| Carriage, total | 2.960 ms | 3.759 ms | 4.750 ms |
| Remote AC publication | 0.943 ms | 1.214 ms | 1.830 ms |
| Attempt + local evidence retention | 2.012 ms | 2.642 ms | 3.063 ms |
| CL + Host custody projection | 2.013 ms | 2.758 ms | 2.849 ms |

The carriage figures deliberately do not claim “delivery latency.” Transport is
in-process in this benchmark so that remote AC and local knowledge remain
separable. Fixture construction is included in suite filesystem counters: the
final run observed 500 `fsync`s for 100 lodgements, while 100 carriage cases
including setup produced 1,600 `fsync`s.

Eight concurrent lodging threads completed 100 Packages at 350 lodgements/s.
Median latency was 13.05 ms and p95 79.02 ms. Filesystem identity locks serialize
same-identity transitions; unrelated identities proceed concurrently. No new
parallel mutation was introduced.

Peak process RSS for the entire 10,000-scale matrix was 120.1 MB. This is a
high-water mark across sequential suites, not steady-state Porter memory.

## ROUNDS

| Tickets | one Round | one changed among N | ten unchanged Rounds | journal growth |
|---:|---:|---:|---:|---:|
| 1 | 1.460 ms | 0.855 ms | 9.785 ms | 410 B |
| 1,000 | 96.0 ms | 82.5 ms | 650.2 ms | 223,187 B |
| 10,000 | 925.8 ms | 920.7 ms | 7.221 s | 2,230,187 B |

Round cost remains linear in Tickets and its journal stores a full observation
per Ticket. Finding one changed Ticket is therefore no cheaper than finding no
change. Frequent attention multiplies both scanning and journal growth. The
Round itself remains Host initiated and observational.

The original implementation also rewrote every Ticket with a duplicate
`TICKET_INSPECTED` event. On APFS, a 1,000-Ticket Round took 14.86 s. Recording
the observation only once in its durable Round journal reduced this to 7.76 s,
a 47.8% improvement. The journal content and PORTER claims did not change.

## Pressure and recovery

Dormant recipient custody is linear through 10,000 Packages:

| Held Packages | wall | storage | files | bytes/Package |
|---:|---:|---:|---:|---:|
| 1,000 | 0.981 s | 647,780 B | 2,000 | 647.8 B |
| 10,000 | 9.456 s | 6,497,780 B | 20,000 | 649.8 B |

At 10,000, immutable AC facts occupy 4,538,890 B and inbox projections
1,958,890 B. File/inode count grows by exactly two per held Package and becomes
the first obvious scarce resource. CPU used 2.14 s of the 9.46 s wall time.
There is no hidden in-memory queue and no retention policy was invented.

Recovery from 10,000 immutable LG facts rebuilt missing Ticket/outgoing
projections in 12.40 s and left 50,000 files using 13.56 MB. A healthy replay
took 722 ms. At 1,000 those values were 920 ms and 78 ms. Rebuild is linear in
total canonical history, even when only current truth is wanted; snapshots have
not yet been earned or implemented.

Canonical facts are not uniformly the storage villain. LG plus its Package body
is large, but Ticket JSON, associations and lock inodes collectively exceed it.
ROUNDS journals dominate the live Butterfly evidence sampled below. Projections
and observation history are therefore at least as important as immutable truth.

## Real Butterfly journey

The live, complete journey `BF:JSNZXWZ7KACR` retained 47 Host Rounds. Its final
Find Me → HarmonicDB correspondence was measured as distinct facts and waits:

```text
LG at Find Me                         t +    0 ms
AC at HarmonicDB                      t +   22 ms
HarmonicDB collection wait                 2,926 ms
HDBE Host processing                       2,866 ms
  of which HDBE execution                  2,860 ms
Return held at Find Me Porter         t +2,992 ms
next Host observation                +    1,106 ms
final Round inspection                      3 ms
Return CL + application continuation       after observation
```

The 2.99 s carriage interval contains recipient Host attention, CL, HDBE and the
Return journey; it is not transport time. Application execution accounts for
almost all of the measured recipient work. The 1.11 s after Return custody is
observation latency. MailWeb revisit starts were roughly 4.1 s apart in this
sample, despite the finer nominal policy; SMTP/MailWeb execution is not PORTER
Round cost.

The updated Stack Inspector measured its resource scan at 1.0 ms. In the live
volumes, Round journals were 54,977 B across 94 files, compared with 10,870 B of
LG, 3,172 B of AC and 1,084 B of CL. It exposes this compact fact/projection view
without becoming a monitoring service.

## Top three and optimization record

1. **ROUNDS duplicated observation into N Tickets.** Threat: accidentally make
   observation unsolicited or lose its evidence. Change: one durable Round
   journal, no duplicate Ticket narration. Result: 47.8% faster at 1,000 on the
   measured APFS baseline; conformance unchanged.
2. **Healthy recovery rematerialized every complete LG projection.** Threat:
   trust projections as truth. Change: verify Ticket, association and terminal
   outgoing/evidence presence, then skip only the locked rewrite; incomplete
   state still rebuilds from LG. Result: 8.38 s to 5.77 s at 1,000 on APFS
   (31.0%); damaged rebuild was unchanged within noise.
3. **Dormancy retained a diagnostic copy of every AC.** Threat: remove evidence
   mistaken for canonical truth. Change: retain AC and inbox unchanged, omit only
   first-acceptance narration; repeated-arrival narration remains. At 10,000 in
   Docker, storage fell 8.81 MB → 6.50 MB (26.2%), wall 11.84 s → 9.83 s
   (17.0%), and durability barriers 55,555 → 44,444.

Three attractive guesses were rejected. Re-serializing smaller projection JSON
did not improve the benchmark. Avoiding diagnostic-log `fsync` barely moved
dormancy and weakened a file that still claimed to be durable, so it was
reverted. Merely avoiding lock `touch`/`chmod` did not improve healthy recovery.
Physical sharding was not attempted because the current IPC filesystem layout is
part of the tested Host ABI; changing it for an APFS symptom would have violated
the freeze without Docker evidence demanding it.

## Maturation pressure record

- Durability is real but not the largest universal cost. On Docker, local
  retained evidence costs more than remote AC; on APFS, directory durability is
  dramatically dearer.
- CL was the most expensive isolated canonical threshold in the final median,
  narrowly above LG; surrounding projection work matters more than the fact name.
- ROUNDS scale well per Ticket but badly with indiscriminate attention and full
  journals. Changed-Ticket discovery remains O(N).
- Healthy recovery is cheap after the fast path; projection reconstruction still
  scales with total history.
- Dormancy consumes disk and, first, inodes. It does not consume Host execution.
- The largest gain was removing duplicate Ticket observation writes.
- No accepted optimization weakened LG, AC, CL, custody, knowledge, isolation,
  Host initiation or the application boundary.
- The clearest rejected architectural shortcut was push notification/change
  delivery toward the Host. It would make ROUNDS cheap by destroying ROUNDS.
- The clearest security pressure is unauthenticated storage exhaustion: any
  reachable sender can force two durable files and roughly 650 B of custody per
  unique accepted identity. Package-size abuse would amplify bytes further.

Security/Introductions, No Web Servers and Continuous Correspondence remain
explicitly unimplemented research horizons.

## Exactly one next maturation experiment

Run **PORTER Introductions under adversarial lodgement**: establish who may make
another Porter cross AC, then measure whether authorization, replay resistance
and bounded refusal prevent custody exhaustion without giving Hosts addresses or
weakening stable Package identity.
