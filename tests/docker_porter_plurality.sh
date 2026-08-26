#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
image=porter-plurality-check
docker build -q -t "$image" . >/dev/null
docker run --rm --network none --entrypoint python \
  -v "$(pwd):/src:ro" -w /src "$image" -m unittest \
  tests.test_evidence_identity tests.test_porter_plurality -v
docker run --rm --network none --entrypoint python -e PYTHONPATH=/src \
  -v "$(pwd):/src:ro" -w /src "$image" \
  benchmarks/porter_plurality.py --samples 20
