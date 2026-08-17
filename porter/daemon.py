from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from .protocol import atomic_write, validate
from .tickets import event, ticket_for_package
from .lodgement import recover
from .carriage import accept, acceptance_evidence, note_attempt, recover_acceptances, retain_evidence
from .custody import recover_collections


class SimulatedCarriageCrash(RuntimeError):
    """Generation IV experiment: transport returned, evidence was not retained."""


class Porter:
    def __init__(self, identity, ipc, routes, transport=None):
        self.identity=identity;self.ipc=Path(ipc);self.routes=routes;self.running=True;self.transport=transport or self._network_deposit
        self.crash_after_response_once=False
        self.ipc.mkdir(parents=True,exist_ok=True);self.ipc.chmod(0o777)
        for name in ("outgoing","inbox","collected","receipts","refused","acceptances","carriage"):
            folder=self.ipc/name;folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o777)
        for lock in (self.ipc/"tickets").glob("CT-*.lock") if (self.ipc/"tickets").exists() else []:lock.chmod(0o666)
        for claimed in (self.ipc/"outgoing").glob("PKG-*.carrying"):
            target=claimed.with_suffix(".json")
            if not target.exists(): claimed.rename(target)
        recover(self.ipc)
        recover_acceptances(self.ipc)
        recover_collections(self.ipc)

    def deposit(self, value, fail_after=None):
        validate(value)
        if value["to"] != self.identity: raise ValueError("recipient Porter refuses this destination")
        if value["expires"] <= int(time.time()): raise ValueError("Package expired before deposit")
        acceptance, repeated = accept(self.ipc, self.identity, value)
        if fail_after == "acceptance": raise RuntimeError("interrupted after durable remote acceptance")
        # AC is already the immutable account of first acceptance. Repeating
        # that fact in an unbounded diagnostic journal consumed a quarter of
        # dormant-custody storage without adding knowledge. A repeated arrival
        # remains useful operational narration because it explains a retry.
        if repeated:
            self.record("PACKAGE_ACCEPTED_AGAIN",value["package"],{"from":value["from"],"kind":value["kind"],"acceptance":acceptance["acceptance"]})
        if value.get("in_reply_to"):
            ticket=ticket_for_package(self.ipc,value["in_reply_to"])
            if ticket:event(self.ipc,ticket,"RETURN_HELD",{"return":value["package"]})
        if fail_after == "evidence": raise RuntimeError("acceptance evidence prevented from returning")
        return acceptance_evidence(acceptance)

    @staticmethod
    def _network_deposit(value, route):
        request=Request(route.rstrip("/")+"/deposit",json.dumps(value,separators=(",",":")).encode(),{"Content-Type":"application/json"},method="POST")
        return json.load(urlopen(request,timeout=10))

    def carry(self):
        while self.running:
            recover(self.ipc)
            for claimed in sorted((self.ipc/"outgoing").glob("PKG-*.carrying")):
                claimed.rename(claimed.with_suffix(".json"))
            for path in sorted((self.ipc/"outgoing").glob("PKG-*.json")):
                try:self.carry_one(path)
                except SimulatedCarriageCrash: raise
                except Exception as exc:self.record("REMOTE_ACCEPTANCE_UNKNOWN",path.stem,{"reason":str(exc)})
            time.sleep(.05)

    def carry_one(self, path, fail_after=None):
        path=Path(path);claimed=path.with_suffix(".carrying")
        try:path.rename(claimed)
        except FileNotFoundError:return
        value=validate(json.loads(claimed.read_text()));note_attempt(self.ipc,value["package"])
        if fail_after == "attempt": raise RuntimeError("interrupted after carriage attempt began")
        try:
            receipt=self.transport(value,self.routes[value["to"]])
            marker=self.ipc/"generation4.acceptance-evidence-lost"
            if self.crash_after_response_once and not marker.exists():
                marker.write_text(value["package"]+"\n")
                raise SimulatedCarriageCrash("recipient accepted; sender crashed before retaining evidence")
            if fail_after == "response": raise RuntimeError("interrupted before acceptance evidence retention")
            knowledge=retain_evidence(self.ipc,receipt)
            self.record("REMOTE_ACCEPTANCE_KNOWN",value["package"],{"recipient":receipt["recipient"],"acceptance":receipt["acceptance"]})
            ticket=ticket_for_package(self.ipc,value["package"])
            if ticket:event(self.ipc,ticket,"REMOTE_ACCEPTANCE_KNOWN",{"recipient":receipt["recipient"],"acceptance":receipt["acceptance"]})
            if fail_after == "retention": raise RuntimeError("interrupted after acceptance evidence retention")
            claimed.unlink(missing_ok=True)
            return knowledge
        except Exception:
            if not (self.ipc/"receipts"/f"{value['package']}.json").exists() and claimed.exists(): claimed.rename(path)
            elif (self.ipc/"receipts"/f"{value['package']}.json").exists(): claimed.unlink(missing_ok=True)
            raise

    def record(self,event_type,package_id,details=None):
        value={"event":event_type,"at_ms":int(time.time()*1000),"porter":self.identity,"package":package_id,**({"details":details} if details else {})}
        with (self.ipc/"porter-events.jsonl").open("a") as stream:
            import fcntl;fcntl.flock(stream,fcntl.LOCK_EX);stream.write(json.dumps(value,separators=(",",":"))+"\n");stream.flush();os.fsync(stream.fileno());fcntl.flock(stream,fcntl.LOCK_UN)


def handler(porter):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def reply(self,status,value):
            raw=json.dumps(value,separators=(",",":")).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self): self.reply(200,{"ok":True,"service":"Porter","identity":porter.identity}) if self.path=="/health" else self.reply(404,{"error":"unknown Porter operation"})
        def do_POST(self):
            if self.path!="/deposit":return self.reply(404,{"error":"unknown Porter operation"})
            try:self.reply(202,porter.deposit(json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))))
            except Exception as exc:self.reply(400,{"protocol":"PORTER/1","kind":"REFUSE","reason":str(exc)})
    return Handler


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--identity",required=True);parser.add_argument("--ipc",default="/ipc");parser.add_argument("--listen",default="0.0.0.0:7070");parser.add_argument("--routes",required=True);parser.add_argument("--experiment-crash-before-acceptance-evidence",action="store_true")
    args=parser.parse_args();porter=Porter(args.identity,args.ipc,json.loads(args.routes));porter.crash_after_response_once=args.experiment_crash_before_acceptance_evidence;threading.Thread(target=porter.carry,daemon=True).start();host,port=args.listen.rsplit(":",1);ThreadingHTTPServer((host,int(port)),handler(porter)).serve_forever()

if __name__=="__main__":main()
