#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
compose="docker compose -f compose.generation5.yaml"
$compose down -v --remove-orphans >/dev/null 2>&1 || true
trap '$compose down -v --remove-orphans >/dev/null 2>&1' EXIT
$compose build >/dev/null
$compose up -d harmonicdb-porter find-me-porter

$compose run --rm find-me-host -c '
from pathlib import Path
from porter.protocol import package
from porter.tickets import lodge
p=package("find-me","harmonicdb","hdbe.call",{"operation":"info","parameters":{},"deposited_at_ms":0},reply_to="find-me")
t=lodge("/ipc",p);Path("/ipc/generation5.ticket").write_text(t["ticket"]);Path("/ipc/generation5.package").write_text(p["package"])
'
ticket="$($compose exec -T find-me-porter cat /ipc/generation5.ticket)"
package="$($compose exec -T find-me-porter cat /ipc/generation5.package)"
deadline=20
while [ "$deadline" -gt 0 ]; do
  if $compose exec -T harmonicdb-porter test -f /ipc/acceptances/"$package".json && $compose exec -T find-me-porter test -f /ipc/receipts/"$package".json; then break; fi
  deadline=$((deadline-1));sleep 1
done
$compose exec -T harmonicdb-porter test -f /ipc/inbox/"$package".json
test "$($compose ps --status running --services harmonicdb-host)" = ""

# The isolated Host initiates Collection and dies immediately after CL crosses.
$compose up -d harmonicdb-host
deadline=20
while [ "$deadline" -gt 0 ]; do
  if [ "$($compose ps --status exited --services harmonicdb-host)" = "harmonicdb-host" ]; then break; fi
  deadline=$((deadline-1));sleep 1
done
collection="$($compose exec -T harmonicdb-porter sh -c 'basename /ipc/collections/facts/CL-*.json .json')"
$compose exec -T harmonicdb-porter test -f /ipc/acceptances/"$package".json
$compose exec -T harmonicdb-porter test -f /ipc/collections/facts/"$collection".json
$compose exec -T harmonicdb-porter test -f /ipc/collected/"$package".json
$compose exec -T harmonicdb-porter test ! -f /ipc/inbox/"$package".json
$compose run --rm --entrypoint sh harmonicdb-host -c 'test ! -f /data/porter-application/'"$collection"'.json'
$compose exec -T harmonicdb-porter sh -c 'test ! -d /ipc/lodgements/lodged || test -z "$(find /ipc/lodgements/lodged -name "LG-*.json" -print -quit)"'

# Restart recovers Host custody, then application processing and Return lodgement
# occur as distinct later facts.
$compose start harmonicdb-host >/dev/null
deadline=30
while [ "$deadline" -gt 0 ]; do
  if $compose exec -T find-me-porter grep -q RETURN_HELD /ipc/tickets/"$ticket".json; then break; fi
  deadline=$((deadline-1));sleep 1
done
$compose exec -T find-me-porter grep -q RETURN_HELD /ipc/tickets/"$ticket".json
$compose run --rm find-me-host -c '
from pathlib import Path
from porter.rounds import make_round
from porter.tickets import collect
t=Path("/ipc/generation5.ticket").read_text();r=make_round("/ipc",[t],"find-me")
assert r["observations"][0]["state"]=="RETURN_HELD",r
answer=collect("/ipc",t)
assert answer["collection"].startswith("CL-"),answer
assert answer["package"]["payload"]["envelope"]["protocol"]=="HDBE/1",answer
'
echo "PORTER Generation V: Host-initiated CL survived the bastard crash; custody recovered before HDBE processing; Return followed later under ordinary PORTER laws."
