#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest -v
if [ "${PORTER_CONFORMANCE_DOCKER:-0}" = "1" ]; then
  for generation in 1 2 3 4 5 6; do "./tests/docker_generation${generation}.sh"; done
fi
echo "PORTER/1 conformance: frozen Generations I-VI semantics passed."
