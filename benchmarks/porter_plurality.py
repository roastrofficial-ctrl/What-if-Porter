from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from porter.carriage import accept
from porter.evidence_identity import EvidenceKeyHistory, key_fact, sign_acceptance
from porter.protocol import package
from porter.threshold import generate_private_key, public_key


def run(n: int, samples: int) -> dict:
    times, bytes_used, files, evidence_bytes = [], [], [], []
    for sample in range(samples):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); value = package("sender", "host", "demo.work", {"sample": sample, "body": "x" * 1024}, ttl=3600)
            statements = []; began = time.perf_counter_ns()
            for index in range(n):
                custodian = f"porter-{index}"; location = root / custodian
                acceptance, _ = accept(location, "host", value)
                continuity, evidence = generate_private_key(), generate_private_key()
                fact = key_fact(continuity, custodian, 0, None, public_key(evidence), activates_at_ms=0, expires_at_ms=2**62)
                EvidenceKeyHistory(custodian, public_key(continuity), [fact])
                statements.append(sign_acceptance(location, custodian, value["package"], fact["evidence_key"], evidence, issued_at_ms=acceptance["accepted_at_ms"] + 1))
            times.append((time.perf_counter_ns() - began) / 1e6)
            stored = [path for path in root.rglob("*") if path.is_file()]
            bytes_used.append(sum(path.stat().st_size for path in stored))
            files.append(len(stored)); evidence_bytes.append(sum(len(json.dumps(item, separators=(",", ":"))) for item in statements))
    return {"n": n, "samples": samples, "accept_and_sign_ms_median": round(statistics.median(times), 3), "custody_files_median": statistics.median(files), "custody_bytes_median": statistics.median(bytes_used), "exported_evidence_bytes_median": statistics.median(evidence_bytes)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--samples", type=int, default=20); parser.add_argument("--scales", default="1,3,5,9"); args = parser.parse_args()
    print(json.dumps([run(int(n), args.samples) for n in args.scales.split(",")], indent=2))


if __name__ == "__main__": main()
