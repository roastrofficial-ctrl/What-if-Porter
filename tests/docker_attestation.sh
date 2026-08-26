#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
image=porter-attestation-check
docker build -q -t "$image" . >/dev/null
docker run --rm --network none --entrypoint python \
  -v "$(pwd):/src:ro" -w /src "$image" -m unittest tests.test_attestation -v
docker run --rm --network none --entrypoint python "$image" -c \
  'import json; from porter.attestation import observe_network_state; print(json.dumps(observe_network_state().evidence(), sort_keys=True))'
docker run --rm --entrypoint python "$image" -c \
  'import json; from porter.attestation import observe_network_state; print(json.dumps(observe_network_state().evidence(), sort_keys=True))'
