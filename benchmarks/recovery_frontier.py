#!/usr/bin/env python3
from __future__ import annotations

import json
import resource
import sys
import tempfile
import time
from pathlib import Path

from porter.custody import recover_collections_for_runtime


def add_fact(root: Path, number: int):
    package_id=f"PKG-{number:032x}";collection=f"CL-{number:032x}"
    package={"protocol":"PORTER/1","package":package_id,"from":"sender",
             "to":"host","kind":"tiny.observe","created":1,
             "expires":4102444800,"payload":{"n":number}}
    fact={"protocol":"PORTER/1","kind":"COLLECTION","collection":collection,
          "package":package,"acceptance":f"AC-{number:032x}","collector":"host",
          "collected_at_ms":number,
          "attests":"PACKAGE_RECOVERABLY_TRANSFERRED_TO_HOST_CUSTODY"}
    (root/"collections"/"facts"/f"{collection}.json").write_text(
        json.dumps(fact,separators=(",",":")))
    (root/"collections"/"by-package"/package_id).write_text(collection+"\n")
    (root/"collected"/f"{package_id}.json").write_text(
        json.dumps(package,separators=(",",":")))
    (root/"collections"/"locks"/f"{package_id}.lock").touch()


def populate(root: Path, total: int):
    for path in (root/"collections"/"facts",root/"collections"/"by-package",
                 root/"collections"/"locks",root/"collected"):
        path.mkdir(parents=True,exist_ok=True)
    for number in range(total):add_fact(root,number)


def measure(root, candidates, shape):
    cpu_began=time.process_time_ns();began=time.perf_counter_ns()
    value=recover_collections_for_runtime(root)
    elapsed=(time.perf_counter_ns()-began)/1e6
    return {"history":candidates,"shape":shape,"mode":value["mode"],
            "startup_ms":round(elapsed,3),
            "cpu_ms":round((time.process_time_ns()-cpu_began)/1e6,3),
            "parsed_facts":value["parsed_facts"],
            "audited_facts":value["audited_facts"],
            "rss_kib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/
                            (1024 if sys.platform=="darwin" else 1))}


def trial(total):
    with tempfile.TemporaryDirectory(prefix="porter-frontier-") as folder:
        root=Path(folder);populate(root,total);results=[]
        results.append(measure(root,total,"cold-no-frontier"))
        results.append(measure(root,total,"clean-warm-audit"))
        add_fact(root,total)
        results.append(measure(root,total+1,"exact-one-fact-extension"))
        (root/"collected"/f"PKG-{total//2:032x}.json").unlink()
        results.append(measure(root,total+1,"missing-projection-forced-full"))
        return results


def main():
    results=[]
    for total in (1000,10000):results.extend(trial(total))
    value={"schema":"PORTER-CANONICAL-RECOVERY-FRONTIER/1","results":results}
    rendered=json.dumps(value,indent=2);print(rendered)
    Path("benchmarks/results/recovery-frontier.json").write_text(rendered+"\n")


if __name__=="__main__":main()
