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


class Porter:
    def __init__(self, identity, ipc, routes, transport=None):
        self.identity=identity;self.ipc=Path(ipc);self.routes=routes;self.running=True;self.transport=transport or self._network_deposit
        self.ipc.mkdir(parents=True,exist_ok=True);self.ipc.chmod(0o777)
        for name in ("outgoing","inbox","collected","receipts","refused"):
            folder=self.ipc/name;folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o777)
        for lock in (self.ipc/"tickets").glob("CT-*.lock") if (self.ipc/"tickets").exists() else []:lock.chmod(0o666)
        recover(self.ipc)

    def deposit(self, value):
        validate(value)
        if value["to"] != self.identity: raise ValueError("recipient Porter refuses this destination")
        if value["expires"] <= int(time.time()): raise ValueError("Package expired before deposit")
        atomic_write(self.ipc/"inbox",value)
        self.record("PACKAGE_HELD",value["package"],{"from":value["from"],"kind":value["kind"]})
        if value.get("in_reply_to"):
            ticket=ticket_for_package(self.ipc,value["in_reply_to"])
            if ticket:event(self.ipc,ticket,"RETURN_HELD",{"return":value["package"]})
        return {"protocol":"PORTER/1","kind":"RECEIPT","package":value["package"],"state":"HELD_FOR_COLLECTION","recipient":self.identity}

    @staticmethod
    def _network_deposit(value, route):
        request=Request(route.rstrip("/")+"/deposit",json.dumps(value,separators=(",",":")).encode(),{"Content-Type":"application/json"},method="POST")
        return json.load(urlopen(request,timeout=10))

    def carry(self):
        while self.running:
            recover(self.ipc)
            for path in sorted((self.ipc/"outgoing").glob("PKG-*.json")):
                claimed=path.with_suffix(".carrying")
                try:path.rename(claimed)
                except FileNotFoundError:continue
                try:
                    value=validate(json.loads(claimed.read_text()));route=self.routes[value["to"]]
                    receipt=self.transport(value,route);atomic_write(self.ipc/"receipts",{**receipt,"package":"PKG-"+value["package"].removeprefix("PKG-")})
                    self.record("DEPOSIT_ACCEPTED",value["package"],{"recipient":receipt.get("recipient")})
                    ticket=ticket_for_package(self.ipc,value["package"])
                    if ticket:event(self.ipc,ticket,"HELD_FOR_COLLECTION",{"recipient":receipt.get("recipient")})
                    claimed.unlink()
                except Exception as exc:
                    refused={"protocol":"PORTER/1","package":value.get("package",claimed.stem),"state":"REFUSED","reason":str(exc)} if "value" in locals() else {"protocol":"PORTER/1","package":claimed.stem,"state":"REFUSED","reason":str(exc)}
                    atomic_write(self.ipc/"refused",refused);claimed.unlink(missing_ok=True)
            time.sleep(.05)

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
    parser=argparse.ArgumentParser();parser.add_argument("--identity",required=True);parser.add_argument("--ipc",default="/ipc");parser.add_argument("--listen",default="0.0.0.0:7070");parser.add_argument("--routes",required=True)
    args=parser.parse_args();porter=Porter(args.identity,args.ipc,json.loads(args.routes));threading.Thread(target=porter.carry,daemon=True).start();host,port=args.listen.rsplit(":",1);ThreadingHTTPServer((host,int(port)),handler(porter)).serve_forever()

if __name__=="__main__":main()
