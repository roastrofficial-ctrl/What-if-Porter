from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .lodgement import lodge as lodge_correspondence, recover
from .custody import collect_package, find_collection


def now_ms(): return int(time.time() * 1000)


@contextmanager
def locked_ticket(ipc, ticket_id):
    root=Path(ipc)/"tickets";root.mkdir(parents=True,exist_ok=True);lock_path=root/(ticket_id+".lock");lock_path.touch(exist_ok=True);lock_path.chmod(0o666);lock=lock_path.open("a+")
    try:
        fcntl.flock(lock,fcntl.LOCK_EX);path=root/(ticket_id+".json");value=json.loads(path.read_text());yield value,path
    finally:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


def event(ipc,ticket_id,kind,details=None):
    with locked_ticket(ipc,ticket_id) as (value,path):
        value["events"].append({"event":kind,"at_ms":now_ms(),**({"details":details} if details else {})})
        temporary=path.with_suffix(".tmp");temporary.write_text(json.dumps(value,separators=(",",":"))+"\n");os.replace(temporary,path)


def lodge(ipc, package):
    return lodge_correspondence(ipc,package)


def ticket_for_package(ipc,package_id):
    path=Path(ipc)/"tickets"/"by-package"/package_id
    return path.read_text().strip() if path.exists() else None


def inspect(ipc,ticket_id,record=True):
    root=Path(ipc)
    with locked_ticket(root,ticket_id) as (value,_):snapshot=dict(value)
    returns=[]
    for path in (root/"inbox").glob("PKG-*.json"):
        candidate=json.loads(path.read_text())
        if candidate.get("in_reply_to")==snapshot["package"]:returns.append(candidate["package"])
    collected_return=snapshot["collected_return"]
    if not collected_return:
        for path in (root/"collections"/"facts").glob("CL-*.json"):
            candidate=json.loads(path.read_text())["package"]
            if candidate.get("in_reply_to")==snapshot["package"]: collected_return=candidate["package"];break
    if collected_return:state="COLLECTED"
    elif snapshot["abandoned"] and returns:state="ABANDONED_WITH_RETURN"
    elif snapshot["abandoned"]:state="ABANDONED"
    elif returns:state="RETURN_HELD"
    elif snapshot["expires"]<=int(time.time()):state="EXPIRED_OBSERVED"
    else:state="OUTSTANDING"
    carriage_path=root/"carriage"/(snapshot["package"]+".json")
    carriage=json.loads(carriage_path.read_text()) if carriage_path.exists() else {"knowledge":"NOT_YET_ATTEMPTED","attempts":[]}
    if record:event(root,ticket_id,"TICKET_INSPECTED",{"observed_state":state,"held_returns":len(returns),"carriage_knowledge":carriage["knowledge"]})
    return {**snapshot,"collected_return":collected_return,"state":state,"held_returns":returns,"duplicate_returns":max(0,len(returns)-1),"carriage_knowledge":carriage["knowledge"],"carriage_attempts":len(carriage["attempts"]),**({"acceptance_evidence":carriage["acceptance_evidence"]} if "acceptance_evidence" in carriage else {})}


def collect(ipc,ticket_id,fail_after=None):
    root=Path(ipc);status=inspect(root,ticket_id,record=False)
    if status["collected_return"]:
        return_id=status["collected_return"];target=root/"collected"/(return_id+".json")
        fact=find_collection(root,return_id)
        if not target.exists() and fact: collect_package(root,return_id,"HOST")
        with locked_ticket(root,ticket_id) as (value,path):
            if not value["collected_return"]:
                value["collected_return"]=return_id;value["events"].append({"event":"RETURN_COLLECTED","at_ms":now_ms(),"details":{"return":return_id,"collection":fact and fact["collection"]}});temporary=path.with_suffix(".tmp");temporary.write_text(json.dumps(value,separators=(",",":"))+"\n");os.replace(temporary,path)
        return {"state":"ALREADY_COLLECTED","return":return_id,"collection":fact and fact["collection"],"package":json.loads(target.read_text())}
    if not status["held_returns"]:return {"state":status["state"],"package":None}
    return_id=sorted(status["held_returns"])[0]
    fact=collect_package(root,return_id,"HOST",fail_after)
    with locked_ticket(root,ticket_id) as (value,path):
        value["collected_return"]=return_id;value["events"].append({"event":"RETURN_COLLECTED","at_ms":now_ms(),"details":{"return":return_id,"collection":fact["collection"]}});temporary=path.with_suffix(".tmp");temporary.write_text(json.dumps(value,separators=(",",":"))+"\n");os.replace(temporary,path)
    return {"state":fact["state"],"return":return_id,"collection":fact["collection"],"package":fact["package"],"duplicates_retained":max(0,len(status["held_returns"])-1)}


def abandon(ipc,ticket_id):
    with locked_ticket(ipc,ticket_id) as (value,path):
        if not value["abandoned"]:value["abandoned"]=True;value["events"].append({"event":"ABANDONED","at_ms":now_ms()});temporary=path.with_suffix(".tmp");temporary.write_text(json.dumps(value,separators=(",",":"))+"\n");os.replace(temporary,path)
    return inspect(ipc,ticket_id,record=False)
