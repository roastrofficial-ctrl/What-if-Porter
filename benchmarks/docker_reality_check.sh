#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)
image="porter-reality-check"
mkdir -p "$root/benchmarks/results"
docker build -q -t "$image" . >/dev/null
docker run --rm --network none --entrypoint python \
  -v "$root/benchmarks:/benchmarks:ro" \
  -v "$root/benchmarks/results:/results" \
  "$image" /benchmarks/reality_check.py "$@"
