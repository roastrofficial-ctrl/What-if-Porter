#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest -v tests.test_native
./benchmarks/docker_reality_check.sh --native --attempts 10000 --samples 100 --quiet --output /results/porter-1.4-final.json
echo "PORTER 1.4 security: authenticated native framing, relocation and asynchronous evidence passed."
