#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from recovery_frontier import populate
from porter.custody import recover_collections_for_runtime


def directory_fingerprint(root):
    return tuple(
        (path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_size)
        for path in (root/"collections"/"facts",
                     root/"collections"/"by-package",root/"collected")
    )


def main():
    with tempfile.TemporaryDirectory(prefix="porter-compaction-") as folder:
        root=Path(folder);populate(root,1000)
        recover_collections_for_runtime(root)
        warm_began=time.perf_counter_ns();warm=recover_collections_for_runtime(root)
        warm_ms=(time.perf_counter_ns()-warm_began)/1e6
        expected=directory_fingerprint(root)
        samples=[]
        for _ in range(1000):
            began=time.perf_counter_ns();clean=directory_fingerprint(root)==expected
            samples.append((time.perf_counter_ns()-began)/1e6)
        association=next((root/"collections"/"by-package").iterdir())
        original=association.read_text();replacement="CL-"+"0"*32+"\n"
        association.write_text(replacement)
        unsafe_after_corruption=directory_fingerprint(root)==expected
        verified=recover_collections_for_runtime(root)
        value={
            "schema":"PORTER-RECOVERY-AUDIT-COMPACTION/1",
            "history":1000,
            "earned_leaf_audit_ms":round(warm_ms,3),
            "earned_leaf_audit_parsed_facts":warm["parsed_facts"],
            "unsafe_root_audit_median_ms":round(statistics.median(samples),6),
            "unsafe_root_audit_claimed_clean_after_leaf_corruption":unsafe_after_corruption,
            "earned_audit_after_corruption":verified["mode"],
            "earned_audit_repaired_association":association.read_text()==original,
        }
        rendered=json.dumps(value,indent=2);print(rendered)
        Path("benchmarks/results/recovery-audit-compaction.json").write_text(rendered+"\n")


if __name__=="__main__":main()
