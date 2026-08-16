from __future__ import annotations
import argparse,json
from pathlib import Path

def lines(path):
    if not path.exists():return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def timeline(sender,recipient,ticket_id):
    sender=Path(sender);recipient=Path(recipient);ticket=json.loads((sender/"tickets"/(ticket_id+".json")).read_text());related={ticket["package"]}
    for item in ticket["events"]:
        if item["event"]=="RETURN_HELD":related.add(item.get("details",{}).get("return"))
    events=[{**item,"actor":"originating Host / local Ticket"} for item in ticket["events"]]
    journal=lines(sender/"porter-events.jsonl")+lines(recipient/"porter-events.jsonl")+lines(recipient/"host-events.jsonl")
    for item in journal:
        if item.get("package") in related or item.get("details",{}).get("in_reply_to")==ticket["package"]:events.append(item)
    return sorted(events,key=lambda x:x["at_ms"])

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--sender",required=True);parser.add_argument("--recipient",required=True);parser.add_argument("--ticket",required=True);args=parser.parse_args()
    for item in timeline(args.sender,args.recipient,args.ticket):print(f"{item['at_ms']}  {item['event']:<24} {item.get('actor') or item.get('porter') or item.get('host')}")
if __name__=="__main__":main()
