#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
image="porter-generation3-proof"
volume="porter-generation3-$PPID-$$"
trap 'docker volume rm -f "$volume" >/dev/null 2>&1 || true' EXIT

docker build -q -t "$image" "$root" >/dev/null
docker volume create "$volume" >/dev/null

docker run --rm --network none --entrypoint python -v "$volume:/ipc" "$image" -c '
from porter.lodgement import SimulatedInterruption,lodge
from porter.protocol import package
p=package("sender","recipient","demo.work",{"crash":"after association"},reply_to="sender")
try:lodge("/ipc",p,lodgement_id="LG-"+"3"*32,ticket_id="CT-"+"4"*32,fail_after="association")
except SimulatedInterruption:pass
else:raise SystemExit("the intended interruption did not occur")
'

docker run --rm --network none --entrypoint python -v "$volume:/ipc" "$image" -c '
from pathlib import Path
from porter.lodgement import recover,resolve
recover("/ipc")
fact=resolve("/ipc","LG-"+"3"*32)
assert fact["state"]=="DEFINITELY_LODGED",fact
root=Path("/ipc")
assert (root/"tickets"/(fact["ticket"]+".json")).exists()
assert (root/"tickets"/"by-package"/fact["package"]).exists()
assert (root/"outgoing"/(fact["package"]+".json")).exists()
'

echo "PORTER Generation III: a new networkless process recovered definite lodgement from the sole canonical LODGED fact."
