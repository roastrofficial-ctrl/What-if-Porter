#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest -v tests.test_rendezvous tests.test_native tests.test_ceremony
python3 benchmarks/rendezvous_continuity.py
echo "PORTER 1.5 security: continuity, stale recovery, replay, conflict and hostile pressure passed."
