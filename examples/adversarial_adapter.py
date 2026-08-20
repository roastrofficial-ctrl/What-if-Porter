#!/usr/bin/env python3
import json
import os
import sys
import time


mode = os.getenv("ADVERSARIAL_ADAPTER", "malformed")
if mode == "bad-ready":
    print("{}", flush=True)
elif mode == "huge-ready":
    print("x" * 70_000, flush=True)
else:
    print(json.dumps({"contract": "PORTER-HOST-ADAPTER/1", "runtime_observation": "ADAPTER_READY"}), flush=True)
    for line in sys.stdin:
        dispatch = json.loads(line)
        if mode == "exit":
            raise SystemExit(7)
        if mode == "hang":
            time.sleep(60)
        elif mode == "huge":
            print("x" * 70_000, flush=True)
        elif mode == "malformed":
            print("{}", flush=True)
        else:
            print(json.dumps({
                "contract": "PORTER-HOST-ADAPTER/1",
                "dispatch": dispatch["dispatch"],
                "runtime_observation": "ADAPTER_RETURNED_CONTROL",
            }), flush=True)
