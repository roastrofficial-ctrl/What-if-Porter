#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
image=porter-native-identity-split-check
docker build -q -t "$image" . >/dev/null
docker run --rm --network none --entrypoint python \
  -v "$(pwd):/src:ro" -w /src "$image" \
  -m unittest tests.test_native_identity_split -v
