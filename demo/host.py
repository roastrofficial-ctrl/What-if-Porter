#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
from porter.protocol import atomic_write,package
from porter.tickets import collect,inspect,lodge

ipc=Path("/ipc");role=os.environ["HOST_ROLE"]
for name in ("outgoing","inbox","collected"): (ipc/name).mkdir(parents=True,exist_ok=True)
if role=="ticket-sender":
    request=package("sender","recipient","demo.echo",{"message":"execution may end"},reply_to="sender");ticket=lodge(ipc,request);(ipc/"generation2.ticket").write_text(ticket["ticket"]);raise SystemExit(0)
if role=="ticket-collector":
    ticket=(ipc/"generation2.ticket").read_text().strip();view=inspect(ipc,ticket)
    if view["state"]!="RETURN_HELD":raise SystemExit("restarted Host found no held Return")
    result=collect(ipc,ticket);(ipc/"generation2.collected").write_text(json.dumps({"ticket":ticket,"state":result["state"],"message":result["package"]["payload"]["message"]}));raise SystemExit(0)
if role=="sender":
    request=package("sender","recipient","demo.echo",{"message":"everything is correspondence"},reply_to="sender")
    atomic_write(ipc/"outgoing",request);(ipc/"sender.deposited").write_text(request["package"])
    deadline=time.time()+20
    while time.time()<deadline:
        for path in (ipc/"inbox").glob("PKG-*.json"):
            value=json.loads(path.read_text())
            if value.get("in_reply_to")==request["package"]:
                path.rename(ipc/"collected"/path.name);(ipc/"sender.collected-return").write_text(value["payload"]["message"]);raise SystemExit(0)
        time.sleep(.05)
    raise SystemExit("sender found no Return to collect")
if role=="recipient":
    deadline=time.time()+20
    while time.time()<deadline:
        for path in (ipc/"inbox").glob("PKG-*.json"):
            value=json.loads(path.read_text());path.rename(ipc/"collected"/path.name)
            (ipc/"recipient.collected").write_text(value["package"])
            atomic_write(ipc/"outgoing",package("recipient",value["reply_to"],"porter.return",{"message":value["payload"]["message"]},in_reply_to=value["package"]))
            raise SystemExit(0)
        time.sleep(.05)
    raise SystemExit("recipient found no Package to collect")
