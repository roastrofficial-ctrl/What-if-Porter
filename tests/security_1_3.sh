#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest -v tests.test_ceremony
./benchmarks/docker_reality_check.sh --ceremony --attempts 10000 --samples 100 --quiet --output /results/porter-1.3-final.json
echo "PORTER 1.3 security: delayed, reordered and adversarial standing ceremony passed."
