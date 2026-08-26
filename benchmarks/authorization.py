from __future__ import annotations

import json
import statistics
import time

from porter.authority import authority_root, derive, generate_keypair, transition
from porter.authorization import authorization_key_id, sign_package, verify_package
from porter.introduction import proof, verify_proof
from porter.protocol import package


def measured(callable_, repetitions: int) -> float:
    samples = []
    for _ in range(repetitions):
        began = time.perf_counter_ns()
        callable_()
        samples.append((time.perf_counter_ns() - began) / 1_000_000)
    return statistics.median(samples)


authority_private, authority_public = generate_keypair()
sender_private, sender_public = generate_keypair()
terms = {
    "kinds": ["signing.request"],
    "max_package_bytes": 16384,
    "max_outstanding_packages": 100,
    "max_outstanding_bytes": 1048576,
    "expires_at": 2000000000,
    "authorization_public_key": sender_public,
    "authorization_generation": 0,
}
root = authority_root("benchmark-authority", authority_public, "signing-host", "find-me", "IN-0", terms)
key_id = authorization_key_id(sender_public, 0, "find-me", "signing-host")
value = package("find-me", "signing-host", "signing.request", {"operation": "sign"}, ttl=3600)
evidence = sign_package(sender_private, value, root=root["root"], introduction="IN-0", authorization_key=key_id, authorization_generation=0)
knowledge = derive(root, [])
hmac_secret = "benchmark-shared-secret"
hmac_evidence = proof(hmac_secret, value)

chains = []
for length in (1, 10, 100, 1000):
    transitions = []
    predecessor = "IN-0"
    for index in range(length):
        successor = f"IN-{index + 1}"
        transitions.append(transition(root, authority_private, predecessor, successor, terms, f"CM-{index}"))
        predecessor = successor
    current = derive(root, transitions)
    current_evidence = sign_package(sender_private, value, root=root["root"], introduction=current["current"], authorization_key=key_id, authorization_generation=0)
    repetitions = 30 if length < 1000 else 5
    chains.append(
        {
            "chain_length": length,
            "derive_plus_verify_median_ms": measured(
                lambda: verify_package(value, current_evidence, root, derive(root, list(reversed(transitions)))),
                repetitions,
            ),
        }
    )

output = {
    "vocabulary": "PORTER-AUTHORIZATION-BENCHMARK/1",
    "hmac_sign_median_ms": measured(lambda: proof(hmac_secret, value), 1000),
    "hmac_verify_median_ms": measured(lambda: verify_proof(hmac_secret, value, hmac_evidence), 1000),
    "ed25519_sign_median_ms": measured(lambda: sign_package(sender_private, value, root=root["root"], introduction="IN-0", authorization_key=key_id, authorization_generation=0), 500),
    "ed25519_verify_median_ms": measured(lambda: verify_package(value, evidence, root, knowledge), 500),
    "fanout_verify_median_ms": {
        str(count): measured(lambda count=count: [verify_package(value, evidence, root, knowledge) for _ in range(count)], 100)
        for count in (1, 3, 9)
    },
    "chains": chains,
    "authorization_evidence_bytes": len(json.dumps(evidence, separators=(",", ":")).encode()),
}
print(json.dumps(output, indent=2))
