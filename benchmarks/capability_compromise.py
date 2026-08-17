#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,resource,tempfile,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from porter.daemon import Porter
from porter.introduction import AdmissionRefused,proof
from porter.protocol import package
from reality_check import count_filesystem_operations,filesystem,measured,percentiles

OLD="compromised-benchmark-capability";NEW="current-benchmark-capability"
def terms(secret,limit=20000):return {"secret":secret,"authority":"technical-passport:offline-claim","kinds":["hdbe.call"],"max_package_bytes":4096,"max_outstanding_packages":limit,"max_outstanding_bytes":limit*4096,"expires_at":int(time.time())+86400}
def value(index,sender="find-me"):return package(sender,"harmonicdb","hdbe.call",{"index":index},ttl=86400)

def refusal_case(count,known):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{},relationships={"find-me":terms(OLD)},require_introductions=True);porter.admission.change("find-me",NEW,terms(NEW),"COMPROMISE_RESPONSE")
        before=filesystem(root)
        def attack():
            for index in range(count):
                item=value(index,"find-me" if known else f"stranger-{index}")
                try:porter.deposit(item,admission=proof(OLD,item) if known else None)
                except AdmissionRefused:pass
        with count_filesystem_operations() as operations:_,timing=measured(attack)
        after=filesystem(root);return {**timing,"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def accepted_current(count):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{},relationships={"find-me":terms(OLD)},require_introductions=True);porter.admission.change("find-me",NEW,terms(NEW,count+1),"COMPROMISE_RESPONSE")
        before=filesystem(root)
        with count_filesystem_operations() as operations:_,timing=measured(lambda:[porter.deposit(item:=value(index),admission=proof(NEW,item)) for index in range(count)])
        after=filesystem(root);return {**timing,"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def blast_radius(limit=50):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{},relationships={"find-me":terms(OLD,limit)},require_introductions=True);accepted=0
        for index in range(limit+1):
            item=value(index)
            try:porter.deposit(item,admission=proof(OLD,item));accepted+=1
            except AdmissionRefused:pass
        legitimate=value(99999)
        try:porter.deposit(legitimate,admission=proof(OLD,legitimate));legitimate_state="AC"
        except AdmissionRefused:legitimate_state="REFUSE"
        return {"allowance":limit,"attacker_accepted":accepted,"legitimate_after_exhaustion":legitimate_state,"resources":filesystem(root)}

def transition_cost(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{},relationships={"find-me":terms(OLD)},require_introductions=True);timings=[]
        before=filesystem(root)
        with count_filesystem_operations() as operations:
            for index in range(samples):
                secret=f"generation-{index}";start=time.perf_counter_ns();porter.admission.change("find-me",secret,terms(secret),"RENEWAL");timings.append(time.perf_counter_ns()-start)
        after=filesystem(root);return {"latency":percentiles(timings),"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--attempts",type=int,default=10000);parser.add_argument("--samples",type=int,default=100);parser.add_argument("--output");parser.add_argument("--quiet",action="store_true");args=parser.parse_args();started=time.time()
    report={"benchmark":"PORTER 1.2 Capability Compromise","attempts":args.attempts,"unknown_refusal":refusal_case(args.attempts,False),"compromised_refusal":refusal_case(args.attempts,True),"current_acceptance":accepted_current(args.attempts),"blast_radius":blast_radius(),"standing_change":transition_cost(args.samples),"elapsed_seconds":time.time()-started}
    raw=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;report["process_max_rss_bytes"]=raw if sys.platform=="darwin" else raw*1024;rendered=json.dumps(report,indent=2,sort_keys=True)
    if args.output:Path(args.output).write_text(rendered+"\n")
    if not args.quiet:print(rendered)
if __name__=="__main__":main()
