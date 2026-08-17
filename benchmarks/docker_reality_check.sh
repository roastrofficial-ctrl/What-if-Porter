#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)
image="porter-reality-check"
mkdir -p "$root/benchmarks/results"
docker build -q -t "$image" . >/dev/null
script="/benchmarks/reality_check.py"
if [ "${1:-}" = "--adversarial" ]; then script="/benchmarks/adversarial_lodgement.py"; shift; fi
if [ "${1:-}" = "--compromise" ]; then script="/benchmarks/capability_compromise.py"; shift; fi
docker run --rm --network none --entrypoint python \
  -v "$root/benchmarks:/benchmarks:ro" \
  -v "$root/benchmarks/results:/results" \
  "$image" "$script" "$@"
