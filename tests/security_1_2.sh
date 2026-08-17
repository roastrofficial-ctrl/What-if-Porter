#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest -v tests.test_introductions tests.test_renewal
./benchmarks/docker_reality_check.sh --compromise --attempts 10000 --samples 100 --quiet --output /results/porter-1.2-final.json
echo "PORTER 1.2 security: standing succession, compromise containment and historical replay passed."
