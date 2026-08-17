#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import resource
import tempfile
import time
from pathlib import Path

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from porter.carriage import accept
from porter.daemon import Porter
from porter.introduction import AdmissionRefused, canonical, package_bytes, proof, verify_proof
from porter.protocol import package
from reality_check import count_filesystem_operations, filesystem, measured, percentiles


def config(limit=20_000):
    return {"find-me":{"secret":"porter-1.1-benchmark-capability","authority":"technical-passport:offline-claim",
        "kinds":["hdbe.call"],"max_package_bytes":4096,"max_outstanding_packages":limit,
        "max_outstanding_bytes":limit*4096,"expires_at":int(time.time())+86400}}


def accepted(count):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);relationships=config();porter=Porter("harmonicdb",root,{},relationships=relationships,require_introductions=True)
        with count_filesystem_operations() as operations:
            _,timing=measured(lambda:[porter.deposit(value:=package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=86400),admission=proof(relationships["find-me"]["secret"],value)) for index in range(count)])
        return {**timing,"resources":filesystem(root),"operations":operations}


def plain_accepted(count):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{})
        with count_filesystem_operations() as operations:
            _,timing=measured(lambda:[porter.deposit(package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=86400)) for index in range(count)])
        return {**timing,"resources":filesystem(root),"operations":operations}


def refused(count):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);porter=Porter("harmonicdb",root,{},relationships=config(),require_introductions=True);before=filesystem(root)
        def attack():
            for index in range(count):
                value=package(f"stranger-{index}","harmonicdb","hdbe.call",{"index":index},ttl=86400)
                try:porter.deposit(value)
                except AdmissionRefused:pass
        with count_filesystem_operations() as operations:_,timing=measured(attack)
        after=filesystem(root)
        return {**timing,"resources_before":before,"resources_after":after,"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}


def security_tax(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);relationships=config(samples*2);secured=Porter("harmonicdb",root/"secured",{},relationships=relationships,require_introductions=True);plain=Porter("harmonicdb",root/"plain",{})
        secured_times=[];plain_times=[];lookup=[];verification=[];policy=[];threshold=[]
        for index in range(samples):
            value=package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=86400);evidence=proof(relationships["find-me"]["secret"],value)
            start=time.perf_counter_ns();secured.admission._fact("find-me");lookup.append(time.perf_counter_ns()-start)
            start=time.perf_counter_ns();verify_proof(relationships["find-me"]["secret"],value,evidence);verification.append(time.perf_counter_ns()-start)
            start=time.perf_counter_ns();size=package_bytes(value);terms=relationships["find-me"];_=(size<=terms["max_package_bytes"] and value["kind"] in terms["kinds"] and terms["expires_at"]>int(time.time()));policy.append(time.perf_counter_ns()-start)
            start=time.perf_counter_ns();secured.deposit(value,admission=evidence);secured_times.append(time.perf_counter_ns()-start)
            other={**value,"package":value["package"].replace("PKG-","PKG-a")};start=time.perf_counter_ns();plain.deposit(other);plain_times.append(time.perf_counter_ns()-start)
        with tempfile.TemporaryDirectory() as threshold_root:
            for index in range(samples):
                value=package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=86400);start=time.perf_counter_ns();accept(Path(threshold_root),"harmonicdb",value);threshold.append(time.perf_counter_ns()-start)
        return {"plain_acceptance":percentiles(plain_times),"authorised_acceptance":percentiles(secured_times),"standing_lookup":percentiles(lookup),"carriage_proof":percentiles(verification),"policy_evaluation":percentiles(policy),"ac_creation":percentiles(threshold)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--attempts",type=int,default=10_000);parser.add_argument("--samples",type=int,default=100);parser.add_argument("--output");parser.add_argument("--quiet",action="store_true");args=parser.parse_args()
    started=time.time();report={"benchmark":"PORTER 1.1 Adversarial Lodgement","attempts":args.attempts,"refused":refused(args.attempts),"plain_accepted":plain_accepted(args.attempts),"accepted":accepted(args.attempts),"security_tax":security_tax(args.samples),"elapsed_seconds":time.time()-started}
    raw=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;report["process_max_rss_bytes"]=raw if sys.platform=="darwin" else raw*1024
    rendered=json.dumps(report,indent=2,sort_keys=True)
    if args.output:Path(args.output).write_text(rendered+"\n")
    if not args.quiet:print(rendered)


if __name__=="__main__":main()
