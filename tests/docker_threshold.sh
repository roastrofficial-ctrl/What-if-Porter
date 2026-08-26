#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
image=porter-threshold-check
docker build -q -t "$image" . >/dev/null
docker run --rm --network none --entrypoint python \
  -v "$(pwd):/src:ro" -w /src "$image" -m unittest \
  tests.test_threshold tests.test_threshold_replication -v
docker run --rm --network none --entrypoint python \
  -e PYTHONPATH=/src -v "$(pwd):/src:ro" -w /src "$image" benchmarks/threshold.py --samples 20
