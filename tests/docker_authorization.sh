#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
image=porter-authorization-check
docker build -q -t "$image" . >/dev/null
docker run --rm --network none --entrypoint python \
  -v "$(pwd):/src:ro" -w /src "$image" \
  -m unittest tests.test_authorization -v
