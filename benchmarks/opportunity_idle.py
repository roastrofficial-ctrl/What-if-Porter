#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys, tempfile, time
from pathlib import Path
from porter.host_runtime import Adapter


def proc(pid):
    status = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if ":" in line: status[line.split(":",1)[0]] = line.split(":",1)[1].strip()
    stat = Path(f"/proc/{pid}/stat").read_text().split()
    return {"rss_kib": int(status["VmRSS"].split()[0]),
            "voluntary": int(status.get("voluntary_ctxt_switches","0")),
            "involuntary": int(status.get("nonvoluntary_ctxt_switches","0")),
            "cpu_ticks": int(stat[13])+int(stat[14])}


def trial(count, script):
    with tempfile.TemporaryDirectory() as folder:
        old={k:os.environ.get(k) for k in ("PORTER_IPC","TINY_HOST_STATE")}
        os.environ.update({"PORTER_IPC":folder,"TINY_HOST_STATE":str(Path(folder)/"state")})
        began=time.perf_counter_ns(); adapters=[Adapter(f"{sys.executable} {script}") for _ in range(count)]; started=time.perf_counter_ns()
        before=[proc(a.process.pid) for a in adapters];time.sleep(10);after=[proc(a.process.pid) for a in adapters]
        for adapter in adapters:adapter.close()
        for key,value in old.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        return {"warm_processes":count,"startup_ms":round((started-began)/1e6,3),
                "idle_seconds":10,"adapter_rss_kib":sum(v["rss_kib"] for v in after),
                "cpu_ticks_delta":sum(b["cpu_ticks"]-a["cpu_ticks"] for a,b in zip(before,after)),
                "voluntary_switches_delta":sum(b["voluntary"]-a["voluntary"] for a,b in zip(before,after)),
                "involuntary_switches_delta":sum(b["involuntary"]-a["involuntary"] for a,b in zip(before,after))}

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--output");args=parser.parse_args();script=Path(__file__).parents[1]/"examples"/"tiny_host_adapter.py"
    value={"schema":"PORTER-OPPORTUNITY-IDLE/1","results":[trial(1,script),trial(4,script)]};rendered=json.dumps(value,indent=2);print(rendered)
    if args.output:Path(args.output).write_text(rendered+"\n")
if __name__=="__main__":main()
