#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,resource,tempfile,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from porter.ceremony import CeremonyRefused,ceremony_proof,verify
from porter.daemon import Porter
from porter.introduction import AdmissionRefused,proof,relationship_id
from porter.protocol import package
from reality_check import count_filesystem_operations,filesystem,measured,percentiles

OLD="benchmark-operational-old";NEW="benchmark-operational-new";ROOT="benchmark-ceremonial-root";EXPIRY=int(time.time())+86400
def terms(secret=OLD):return {"secret":secret,"authority":"offline-claim","kinds":["hdbe.call"],"max_package_bytes":4096,"max_outstanding_packages":20000,"max_outstanding_bytes":81920000,"expires_at":EXPIRY}
def config():
    value=terms();value.update({"ceremony_secret":ROOT,"ceremony_expires_at":EXPIRY,"ceremony_max_changes":200,"ceremony_max_pending":8,"ceremony_terms":{key:value[key] for key in ("kinds","max_package_bytes","max_outstanding_packages","max_outstanding_bytes","expires_at")}});return value
def pair(root):return Porter("find-me",root/"a",{},relationships={"harmonicdb":config()},require_introductions=True),Porter("harmonicdb",root/"b",{},relationships={"find-me":config()},require_introductions=True)

def valid(samples):
    preparation=[];verification=[];recipient=[];total=[]
    with tempfile.TemporaryDirectory() as temporary:
        a,b=pair(Path(temporary));predecessor=relationship_id("harmonicdb","find-me");before=filesystem(Path(temporary))
        with count_filesystem_operations() as operations:
            for index in range(samples):
                started=time.perf_counter_ns();value=a.ceremonies.draft("harmonicdb",predecessor,f"new-{index}",terms(f"new-{index}"),"RENEWAL");a.ceremonies.lodge(value);preparation.append(time.perf_counter_ns()-started)
                evidence=ceremony_proof(ROOT,value);started=time.perf_counter_ns();assert verify(ROOT,value,evidence);verification.append(time.perf_counter_ns()-started)
                started=time.perf_counter_ns();b.ceremonies.receive(value,evidence);recipient.append(time.perf_counter_ns()-started);total.append(preparation[-1]+recipient[-1]);predecessor=value["successor"]
        after=filesystem(Path(temporary));return {"origin_durable_preparation":percentiles(preparation),"proof_verification":percentiles(verification),"recipient_verification_candidate_sc_result":percentiles(recipient),"total_without_transport_delay":percentiles(total),"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def invalid(count):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);a,b=pair(root);before=filesystem(root)
        def attack():
            for index in range(count):
                value=a.ceremonies.draft("harmonicdb",relationship_id("harmonicdb","find-me"),NEW,terms(NEW),"FAKE",ceremony_id=f"CM-hostile-{index}")
                try:b.ceremonies.receive(value,ceremony_proof("wrong-root",value))
                except CeremonyRefused:pass
        with count_filesystem_operations() as operations:_,timing=measured(attack)
        after=filesystem(root);return {**timing,"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def operational_controls(count):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{},relationships={"find-me":config()},require_introductions=True)
        def unknown():
            for index in range(count):
                value=package(f"stranger-{index}","harmonicdb","hdbe.call",{"index":index},ttl=3600)
                try:porter.deposit(value)
                except AdmissionRefused:pass
        _,timing=measured(unknown);return timing

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--attempts",type=int,default=10000);parser.add_argument("--samples",type=int,default=100);parser.add_argument("--output");parser.add_argument("--quiet",action="store_true");args=parser.parse_args();started=time.time()
    report={"benchmark":"PORTER 1.3 Standing Ceremony Correspondence","attempts":args.attempts,"valid_ceremony":valid(args.samples),"invalid_ceremony_refusal":invalid(args.attempts),"ordinary_unknown_refusal":operational_controls(args.attempts),"elapsed_seconds":time.time()-started}
    raw=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;report["process_max_rss_bytes"]=raw if sys.platform=="darwin" else raw*1024;rendered=json.dumps(report,indent=2,sort_keys=True)
    if args.output:Path(args.output).write_text(rendered+"\n")
    if not args.quiet:print(rendered)
if __name__=="__main__":main()
