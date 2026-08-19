# PORTER Host Runtime — Pressure Record

## Verdict

The Host Runtime was earned.

One unchanged, single-threaded runtime now operates both real Butterfly Hosts:

- Find Me, through a warm PHP/Laravel adapter that owns MailWeb, ROUNDS and application continuation;
- HarmonicDB, through a warm Python adapter that owns HDBE execution, effects, recovery and Return production.

The runtime knows neither MailWeb nor HDBE. It knows only local PORTER custody,
configured Kind selection, explicit Collection, bounded batches, adapter control
transfer, local attention and shutdown. Both Hosts remain `network_mode: none`.
Arrival still cannot wake either Host.

This is useful substrate, but not yet a product. **PorterNet** remains a coherent
research-horizon name for a possible practical PORTER ecosystem; nothing in this
experiment renames or broadens PORTER.

## The duplication before extraction

| Concern | Find Me before | HarmonicDB before | Runtime now |
|---|---|---|---|
| Lifetime | persistent Artisan command | persistent Python host | persistent local runtime plus warm adapter |
| Bootstrap | Laravel bootstrap | Python/HarmonicDB bootstrap | adapter-specific and measured, not interpreted |
| Inspection | scan local Porter IPC | scan local Porter IPC | scan local custody on a Host-chosen visit |
| Selection | `mailweb.request` | `hdbe.call` | configured opaque Kind allow-list |
| Collection | PHP Porter client | Python Porter library | canonical PORTER Collection |
| Dispatch | MailWeb router | HDBE executor | one `COLLECTION` fact over JSON lines |
| Batching | application loop | application loop | bounded, single-stream batch |
| Attention | active ROUNDS versus ordinary idle | computational polling cadence | adapter may request a bounded next visit |
| Restart | application-specific recovery | application-specific recovery | runtime redelivers ambiguous Collection; adapter decides meaning |
| Shutdown | loop-specific | loop-specific | signal sets a stop boundary between dispatches |
| Return | MailWeb/HDBE clients | HDBE result and Porter client | application-owned |
| Concurrency | one process | one process | one process; deliberately unchanged |

The common lifecycle is therefore small:

```text
HOST STARTS LOCALLY
  → RUNTIME CHOOSES A VISIT
  → INSPECT LOCAL PORTER CUSTODY
  → SELECT BY CONFIGURED KIND
  → EXPLICIT COLLECTION
  → HAND THE COLLECTION FACT TO THE APPLICATION ADAPTER
  → APPLICATION WORK / OPTIONAL LODGEMENT
  → ADAPTER RETURNS CONTROL
  → CONTINUE, IDLE, OR STOP
```

## The application boundary

`PORTER-HOST-ADAPTER/1` is deliberately a language-neutral JSON-lines contract
over local standard input/output. A warm adapter first emits `ADAPTER_READY`.
For each dispatch the runtime sends a dispatch identity and the complete,
canonical `COLLECTION` fact. The adapter returns only
`ADAPTER_RETURNED_CONTROL` with the same dispatch identity and may request a
`next_visit_ms` value.

Returning control is an operational observation. It is not `PROCESSED`,
`COMPLETED`, `FAILED`, application acknowledgement or a PORTER disposition. The
runtime's durable `dispatch-returned/PKG-….json` marker prevents needless replay
after an unambiguous return, while an adapter death before that threshold leaves
the Collection eligible for redelivery. Application records decide whether an
effect or Return must be repeated.

This boundary has one intentional Python implementation dependency today: the
runtime itself uses the existing Python PORTER library. The adapter contract does
not. PHP Find Me and Python HarmonicDB use exactly the same runtime executable.

## Ownership line

The runtime owns:

- local startup and shutdown mechanics;
- Host-chosen inspection of an already local Porter boundary;
- configured Kind selection without payload interpretation;
- explicit Collection and Collection recovery;
- bounded, serial dispatch;
- warm adapter lifetime;
- bounded local idle policy and operational timing observations.

The application adapter owns:

- MailWeb or HDBE parsing and validation;
- all application effects and transactions;
- success, failure, retry and recovery meaning;
- ROUNDS and continuation state;
- deciding whether and what to lodge as further correspondence;
- requesting more or less attention while the runtime enforces local bounds.

The Porter owns arrival, custody and the immutable `LG → AC → CL` evidence. It
does not start, signal, call or wake the runtime.

## RendezvousUnavailable was not a runtime failure

The already-lodged Package was
`PKG-c9c168f9ebf954cbb5bc9b7b6829b349`, bound to Lodgement
`LG-8c7090585ba8f9ccf0df1a8ab10f6286`. Its generation-5 rendezvous fact had
expired four seconds before lodgement. `RendezvousUnavailable` was therefore a
truthful PORTER 1.5 knowledge state, not evidence about runtime execution.

Authenticated knowledge was restored through the existing native continuity
carriage with the signed generation-6 fact
`RV-bd3260cdd14b970a48efffad18b35f6b`. The recipient-local lab continuity trust
root was explicitly re-identified because the former experiment authority's
private material had not been retained. No static location edit or application
semantic was added to the runtime.

After continuity, Find Me reported `CURRENT_RENDEZVOUS_KNOWN` and the exact
outgoing native Unit resumed. The canonical Lodgement SHA-256 remained
`8a17d7e512d73955eeaf2f9dd774f0eddd78fa14d0a1bca64394e6c9bea97a73`;
the Unit digest remained
`e8be09b802faadac338620d30f8089ac69e8be021f3dbe52f5864a29376ee3bd`.
The Package itself had expired while the authority decision was pending, so the
recipient correctly refused it as `CORRESPONDENCE_NOT_ADMITTED`. That refusal
proves the resumed Package was unchanged; replacing or extending it would have
made the test dishonest.

## Workload measurements

These are local-container experiments, not general capacity claims. Warm time
excludes adapter startup; episodic time includes it. Times are milliseconds.

| Host | Packages | Episodic total | Warm work | Warm median dispatch |
|---|---:|---:|---:|---:|
| Find Me | 0 | 52.790 | 0.065 | — |
| Find Me | 1 | 58.889 | 8.379 | 5.296 |
| Find Me | 10 | 88.762 | 42.663 | 1.595 |
| Find Me | 100 | 602.261 | 523.876 | 1.617 |
| HarmonicDB | 0 | 59.564 | 0.085 | — |
| HarmonicDB | 1 | 69.499 | 13.363 | 7.237 |
| HarmonicDB | 10 | 166.170 | 104.961 | 5.705 |
| HarmonicDB | 100 | 1281.873 | 1132.952 | 6.316 |

Measured adapter startup was 46.462–50.619 ms for Find Me and
43.260–48.759 ms for HarmonicDB. Keeping each adapter warm plainly earns its
complexity.

### Batch and backlog pressure

| Host | Batch | 100 elapsed ms | Throughput/s | Oldest ms | Newest ms |
|---|---:|---:|---:|---:|---:|
| Find Me | 1 | 720.936 | 138.71 | 12 | 720 |
| Find Me | 10 | 554.585 | 180.31 | 9 | 554 |
| Find Me | 25 | 599.944 | 166.68 | 13 | 600 |
| Find Me | 100 | 660.315 | 151.44 | 18 | 660 |
| HarmonicDB | 1 | 1262.070 | 79.23 | 15 | 1260 |
| HarmonicDB | 10 | 880.483 | 113.57 | 14 | 876 |
| HarmonicDB | 25 | 682.651 | 146.49 | 8 | 682 |
| HarmonicDB | 100 | 676.172 | 147.89 | 8 | 676 |

Find Me therefore uses batch 10 and HarmonicDB batch 25. At backlog 500 they
processed 110.92/s and 108.39/s respectively, with newest-item latency about
4.5 seconds. When 100 items arrived behind 10 already being handled, Find Me
completed 110 in 743.542 ms and HarmonicDB in 738.116 ms. Larger batches flatten
or regress; no measurement earns runtime concurrency, so none was added.

## Idle cost and attention

After the final real journey, a ten-second idle observation found:

| Host | Runtime RSS | Voluntary switches | Non-voluntary | Journal growth | Container memory |
|---|---:|---:|---:|---:|---:|
| Find Me | 14,740 KiB | +39 | +0 | 0 bytes | 41.67 MiB |
| HarmonicDB | 13,180 KiB | +191 | +1 | 0 bytes | 21.79 MiB |

Docker's point samples were 0.17% CPU and 0.31% CPU respectively. The journal
does not grow on empty visits.

Application-specific attention survived abstraction. A Find Me response bearing
MailWeb `revisit` requested and received a 10 ms next visit; the completed page
requested and received 250 ms. HarmonicDB independently requested 50 ms. The
runtime merely clamps requests to its configured local bounds. ROUNDS remain
Find Me application behaviour.

## Crash and shutdown evidence

For each real adapter, ten Packages were lodged and the process was forced to
die after application handling of dispatch two but before returning runtime
control. Each first run exited non-zero with exactly one runtime-return marker.
Restart then produced ten markers and ten Collection facts with all Package
identities unchanged. The application-owned crash marker, not the runtime,
decided how the ambiguous second dispatch recovered.

The unit experiment also stops between dispatches: one Package crosses the
return-control threshold, two remain in recoverable custody, and restart handles
the remaining two without losing or inventing identity. SIGTERM and SIGINT set
that same between-dispatch stop boundary; the adapter is then closed locally.

## Real journey and invariant check

A fresh real request completed as:

```text
Postbox
  → Porter
  → networkless Find Me Host
  → Porter
  → networkless HarmonicDB Host
  → Return
  → later Find Me Round
  → SERVED WITHOUT A WEB SERVER
```

The HDBE Package was `PKG-e6a29db53f16d881dcceec9673b75899`; the later Round
was `RD-b1f9b35400a75ed4f72015d64702a1dd`; the Return Collection was
`CL-7f94e41ef8591551c924582f1f239c63`. Both Host network tables contained only
headers and Docker reported zero network I/O. Find Me's process tree contained
only PID 1 `porter-host-runtime` and its warm `php artisan mailweb:adapter`.

The installed Porter image passed all 85 unit tests. Find Me's adapter passed PHP
lint and its application health command. The new runtime-specific suite covers
batch bounds, opaque Kind policy, the non-disposition threshold, bounded
attention, mid-batch crash and Host-chosen shutdown.

## Pressure, not product

The abstraction ends in the right place: it removes duplicated lifecycle code
without absorbing application meaning. Its current filesystem scan gives simple,
recoverable truth but causes polling wakeups and backlog tail latency. The
single-stream results are already adequate for this experiment and do not
justify a worker pool, scheduling framework, remote control plane or generic job
semantics.

The exactly one next experiment is **indexed local attention**: test whether a
Porter-maintained, recoverable candidate projection can make empty inspection
and large-backlog selection cheaper while preserving the absolute rule that it
cannot wake, signal or invoke the Host. No concurrency or product surface is
part of that experiment.

