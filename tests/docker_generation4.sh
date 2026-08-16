#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
compose="docker compose -f compose.generation4.yaml"
$compose down -v --remove-orphans >/dev/null 2>&1 || true
trap '$compose down -v --remove-orphans >/dev/null 2>&1' EXIT
$compose build >/dev/null
$compose up -d harmonicdb-porter find-me-porter

# A networkless Find Me execution lodges real HDBE/1 correspondence, then ends.
$compose run --rm find-me-host -c '
from pathlib import Path
from porter.protocol import package
from porter.tickets import lodge
p=package("find-me","harmonicdb","hdbe.call",{"operation":"info","parameters":{},"deposited_at_ms":0},reply_to="find-me")
t=lodge("/ipc",p)
Path("/ipc/generation4.ticket").write_text(t["ticket"])
Path("/ipc/generation4.package").write_text(p["package"])
'
ticket="$($compose exec -T find-me-porter cat /ipc/generation4.ticket)"
package="$($compose exec -T find-me-porter cat /ipc/generation4.package)"
deadline=20
while [ "$deadline" -gt 0 ]; do
  if $compose exec -T harmonicdb-porter test -f /ipc/acceptances/"$package".json; then break; fi
  deadline=$((deadline-1)); sleep 1
done
$compose exec -T harmonicdb-porter test -f /ipc/acceptances/"$package".json
$compose exec -T harmonicdb-porter test -f /ipc/inbox/"$package".json
$compose exec -T find-me-porter test ! -f /ipc/receipts/"$package".json
$compose exec -T find-me-porter grep -q ACCEPTANCE_UNKNOWN /ipc/carriage/"$package".json

# Only a new Host execution observes the epistemic gap.
$compose run --rm find-me-host -c '
from pathlib import Path
from porter.rounds import make_round
t=Path("/ipc/generation4.ticket").read_text()
r=make_round("/ipc",[t],"find-me")
assert r["observations"][0]["carriage_knowledge"]=="ACCEPTANCE_UNKNOWN",r
'

# Restart without the fault. Repeated identity recovers the original acceptance.
$compose stop find-me-porter >/dev/null
$compose run -d --name porter-generation4-restarted-find-me-porter --service-ports --use-aliases --entrypoint porter find-me-porter --identity find-me --routes '{"harmonicdb":"http://harmonicdb-porter:7070"}' >/dev/null
deadline=20
while [ "$deadline" -gt 0 ]; do
  if $compose exec -T harmonicdb-porter test -f /ipc/acceptances/"$package".json && docker exec porter-generation4-restarted-find-me-porter test -f /ipc/receipts/"$package".json; then break; fi
  deadline=$((deadline-1)); sleep 1
done
docker exec porter-generation4-restarted-find-me-porter grep -q REMOTE_ACCEPTANCE_KNOWN /ipc/carriage/"$package".json
test "$($compose exec -T harmonicdb-porter find /ipc/acceptances -name "$package.json" | wc -l | tr -d ' ')" = 1

# Find Me still learns only by looking. Then the isolated real HDBE Host collects,
# computes, and lodges an ordinary Return which Find Me later collects.
$compose run --rm find-me-host -c '
from pathlib import Path
from porter.rounds import make_round
t=Path("/ipc/generation4.ticket").read_text()
r=make_round("/ipc",[t],"find-me")
assert r["observations"][0]["carriage_knowledge"]=="REMOTE_ACCEPTANCE_KNOWN",r
'
$compose up -d harmonicdb-host
deadline=30
while [ "$deadline" -gt 0 ]; do
  if docker exec porter-generation4-restarted-find-me-porter grep -q RETURN_HELD /ipc/tickets/"$ticket".json; then break; fi
  deadline=$((deadline-1)); sleep 1
done
$compose run --rm find-me-host -c '
from pathlib import Path
from porter.rounds import make_round
from porter.tickets import collect
t=Path("/ipc/generation4.ticket").read_text()
r=make_round("/ipc",[t],"find-me")
assert r["observations"][0]["state"]=="RETURN_HELD",r
answer=collect("/ipc",t)
assert answer["package"]["payload"]["envelope"]["protocol"]=="HDBE/1",answer
'
echo "PORTER Generation IV: remote acceptance became fact before local knowledge; repeated Package identity recovered evidence; Hosts remained silent until ROUNDS and collection."
