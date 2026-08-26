from __future__ import annotations

import json
import statistics
import time

from porter.authority import authority_root, derive, generate_keypair, transition


def measured(callable_, repetitions: int) -> float:
    samples = []
    for _ in range(repetitions):
        began = time.perf_counter_ns()
        callable_()
        samples.append((time.perf_counter_ns() - began) / 1_000_000)
    return statistics.median(samples)


private, public = generate_keypair()
root = authority_root(
    "benchmark-authority",
    public,
    "signing-host",
    "find-me",
    "IN-0",
    {"kinds": ["signing.request"], "limit": 1000},
)

results = []
for length in (1, 10, 100, 1000):
    values = []
    predecessor = "IN-0"
    for index in range(length):
        successor = f"IN-{index + 1}"
        values.append(
            transition(
                root,
                private,
                predecessor,
                successor,
                {"kinds": ["signing.request"], "limit": 1000 - index},
                f"CM-{index}",
            )
        )
        predecessor = successor
    repetitions = 30 if length < 1000 else 5
    results.append(
        {
            "chain_length": length,
            "verify_and_derive_median_ms": measured(lambda: derive(root, list(reversed(values))), repetitions),
            "encoded_evidence_bytes": len(json.dumps(values, separators=(",", ":")).encode()),
        }
    )

fork_x = transition(root, private, "IN-0", "IN-X", {"limit": 1}, "CM-X")
fork_y = transition(root, private, "IN-0", "IN-Y", {"limit": 1}, "CM-Y")
output = {
    "vocabulary": "PORTER-AUTHORITY-BENCHMARK/1",
    "sign_transition_median_ms": measured(
        lambda: transition(root, private, "IN-0", "IN-X", {"limit": 1}, "CM-benchmark"),
        100,
    ),
    "fork_verify_and_detect_median_ms": measured(lambda: derive(root, [fork_x, fork_y]), 100),
    "chains": results,
}
print(json.dumps(output, indent=2))
