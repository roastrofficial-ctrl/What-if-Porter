# PORTER Elastic Opportunity Stability under Mixed Latency

Status: experiment complete, 2026-08-20.

This experiment challenges the first elastic policy's weakest assumption: that
one recent slow adapter return is sufficient evidence for every subsequent
capacity increase. It tests whether process-local, Kind-opaque evidence can
distinguish one outlier from alternating, clustered, and sustained slowness
without granting arrival causal power or creating durable scheduler truth.

All frozen PORTER and Host adapter semantics remain unchanged.

## Failure criterion

The stability policy fails if it starves unrelated work behind one slow call,
inflates the complete pool for one outlier, materially damages sustained-slow
throughput, oscillates during a stable mixed workload, remembers pressure after
restart, interprets Kind, or writes its observations durably.

## Policy

The Runtime retains only the last eight completed adapter control intervals in
memory and combines them with currently slow adapter calls. Evidence is bounded
in both count and lifetime.

Capacity `C` requires at least `C` pieces of slow evidence before growing to
`C + 1`:

- at one adapter, one slow outstanding offer earns a second lane so unrelated
  correspondence cannot be monopolised;
- at two adapters, two independent recent or active slow observations are
  required for a third;
- at three, three are required for the fourth.

This proportional rule is deliberately not a workload classifier. It neither
examines Kind nor predicts application meaning. It asks only whether the Host's
recent chosen offers justify paying for another independent opportunity.

Shedding has separate hysteresis. Eight consecutive cheap completed intervals,
no currently slow dispatch, an unused adapter, and a minimum capacity residence
permit one process to retire during continuing backlog. Complete local idleness
retains the previous idle-shedding rule. Growth and shedding each occur at most
once per chosen visit.

The configurable operational controls are:

```text
--elastic-slow-offer-ms 5
--elastic-evidence-window 8
--elastic-minimum-residence-ms 50
--elastic-shed-after-ms 1000
```

They are deployment policy, not protocol values.

## A useful falsification

The first elastic implementation measured from the beginning of adapter
dispatch until the Runtime reaped the completed future. Returned-control marker
publication and filesystem delay could therefore masquerade as application
slowness. A zero-delay workload grew to four.

That policy was rejected. Measurement now ends immediately when the unchanged
adapter `dispatch()` returns control. CL work, marker publication, candidate
inspection, and delayed reaping cannot vote for capacity. The zero-delay
conformance vector remains at one.

## Mixed-latency pressure

Each workload contains 60 candidates. Slow calls take 30 ms; cheap calls return
immediately. Every new elastic adapter pays a modeled 45 ms Tiny startup cost.
The control is the superseded single-sample policy; the candidate policy is the
bounded eight-sample evidence window with hysteresis.

| Workload | Single-sample drain | Stable drain | Single peak | Stable peak |
|---|---:|---:|---:|---:|
| One slow, then 59 cheap | 848 ms | 1,067 ms | 3 | 2 |
| Alternating cheap/slow | 860 ms | 854 ms | 4 | 4 |
| 15 cheap, 20 slow, 25 cheap | 1,040 ms | 1,081 ms | 4 | 4 |
| 60 slow | 1,148 ms | 1,168 ms | 4 | 4 |

The isolated outlier is the discriminating result. Single-sample elasticity
created two extra processes and reached three; proportional evidence created
only the one escape lane justified by the blocked offer. That restraint cost
219 ms in this filesystem-heavy run because the unnecessarily created third
lane also accelerated unrelated local publication. The experiment accepts that
trade: avoiding unjustified capacity is the objective, not maximizing throughput
by allowing application latency to accidentally authorize filesystem workers.

For alternating pressure both policies reached four and the stable policy was
0.8% faster. Clustered pressure was 4.0% slower and sustained pressure 1.7%
slower—small costs for requiring independent evidence. Every workload returned
to one adapter. No workload oscillated repeatedly between growth and shedding.

Raw observations are in `benchmarks/results/mixed-latency.json`.

## Explicit shapes

Conformance tests establish:

- Package arrival without a chosen Runtime visit creates no process;
- a genuinely cheap application never grows, regardless of filesystem cost;
- one slow outlier grows only from one to two;
- clustered slow work can earn all four and trailing cheap work permits
  shedding;
- sustained slowness still reaches the configured bound;
- a hung first offer still permits unrelated work through the second lane;
- restart begins with one adapter and an empty evidence window;
- no RUNNING, PROCESSING, worker, lease, capacity, or latency fact is durable.

On crash, the evidence window, residence timer, starting capacity, and pool all
vanish. CL and returned-control marker recovery are exactly as before. Restart
does not inherit an entitlement to scale.

## Verdict

The evidence window earns itself. A single slow observation retains the crucial
escape property but cannot inflate the complete pool. Repeated and concurrent
slowness still earns capacity with negligible sustained-work regression.
Hysteresis allows cheap phases to shed without embedding application classes or
fairness policy.

Serial remains the default; fixed capacity remains simplest for continuously
slow applications; stable elasticity remains opt-in for mixed or bursty Hosts.

The one next experiment is **Attention Loop Inspection Decoupling**: separate
cheap completion reaping from expensive candidate re-enumeration, and determine
whether a bounded process-local pressure snapshot can preserve identical
selection and arrival causality while eliminating repeated large-directory
inspection during full or slowly changing capacity.
