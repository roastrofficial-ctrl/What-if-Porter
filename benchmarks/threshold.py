from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from porter.carriage import accept, acceptance_evidence
from porter.threshold import custody_claim, draft, generate_private_key, public_key, reconcile, roster


def median(values):
    return round(statistics.median(values), 3)


def run(scale: int, samples: int) -> dict:
    standing = generate_private_key()
    keys = [generate_private_key() for _ in range(scale)]
    members = [{"porter": f"p{index}", "endpoint": f"p{index}:7410", "signing_key": public_key(key)} for index, key in enumerate(keys)]
    roster_fact = roster("harmonicdb", members, scale // 2 + 1, standing, effective_from=1)
    drafted, accepted, reconciled, sizes = [], [], [], []
    for sample in range(samples):
        with tempfile.TemporaryDirectory() as temporary:
            began = time.perf_counter_ns()
            deposit, packages = draft(roster_fact, "find-me", "hdbe.call", {"sample": sample}, created=100)
            drafted.append((time.perf_counter_ns() - began) / 1e6)
            claims = []
            began = time.perf_counter_ns()
            for index, (key, value) in enumerate(zip(keys, packages)):
                acceptance, _ = accept(Path(temporary) / f"p{index}", "harmonicdb", value)
                receipt = acceptance_evidence(acceptance)
                claims.append(custody_claim(roster_fact, deposit, f"p{index}", value, receipt, key))
            accepted.append((time.perf_counter_ns() - began) / 1e6)
            began = time.perf_counter_ns()
            fact = reconcile(roster_fact, deposit, claims, observed_at=200)
            reconciled.append((time.perf_counter_ns() - began) / 1e6)
            sizes.append(sum(len(json.dumps(item, separators=(",", ":"))) for item in [deposit, fact, *packages, *claims]))
    return {"n": scale, "m": scale // 2 + 1, "samples": samples, "draft_ms_median": median(drafted), "accept_and_sign_ms_median": median(accepted), "reconcile_ms_median": median(reconciled), "evidence_bytes_median": median(sizes)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--scales", default="1,3,5,9")
    args = parser.parse_args()
    print(json.dumps([run(int(scale), args.samples) for scale in args.scales.split(",")], indent=2))


if __name__ == "__main__":
    main()
