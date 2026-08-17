#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
compose="docker compose -f compose.generation6.yaml"
trap '$compose down -v --remove-orphans >/dev/null 2>&1' EXIT
$compose build >/dev/null

run_case() {
  point="$1"
  export PORTER_CRASH_POINT="$point"
  $compose down -v --remove-orphans >/dev/null 2>&1 || true
  $compose up -d harmonicdb-porter find-me-porter
  $compose run --rm find-me-host -c '
from pathlib import Path
import os
from porter.protocol import package
from porter.tickets import lodge
point=os.environ["PORTER_CRASH_POINT"]
p=package("find-me","harmonicdb","hdbe.call",{"operation":"append","parameters":{"store":"find_me","domain":"journey","coordinate":"GEN6-"+point,"values":{"generation_six_probe":42.0},"maintain_semantic_indexes":False},"deposited_at_ms":0},reply_to="find-me")
t=lodge("/ipc",p);Path("/ipc/generation6.ticket").write_text(t["ticket"]);Path("/ipc/generation6.package").write_text(p["package"])
'
  ticket="$($compose exec -T find-me-porter cat /ipc/generation6.ticket)"
  package="$($compose exec -T find-me-porter cat /ipc/generation6.package)"
  deadline=20
  while [ "$deadline" -gt 0 ]; do
    if $compose exec -T harmonicdb-porter test -f /ipc/inbox/"$package".json; then break; fi
    deadline=$((deadline-1));sleep 1
  done
  $compose up -d harmonicdb-host
  deadline=120
  while [ "$deadline" -gt 0 ]; do
    if [ "$($compose ps --status exited --services harmonicdb-host)" = "harmonicdb-host" ]; then break; fi
    deadline=$((deadline-1));sleep 1
  done
  collection="$($compose exec -T harmonicdb-porter sh -c 'basename /ipc/collections/facts/CL-*.json .json')"
  $compose exec -T harmonicdb-porter test -f /ipc/collections/facts/"$collection".json
  $compose run --rm --entrypoint sh harmonicdb-host -c 'test -f /data/porter-application/'"$collection.$point.crashed"

  case "$point" in
    after_read)
      $compose run --rm --entrypoint sh harmonicdb-host -c 'test ! -f /data/porter-application/'"$collection.result.json" ;;
    after_effect)
      $compose run --rm --entrypoint sh harmonicdb-host -c 'test ! -f /data/porter-application/'"$collection.result.json" ;;
    after_application_record)
      $compose run --rm --entrypoint sh harmonicdb-host -c 'test -f /data/porter-application/'"$collection.result.json"' && test ! -f /data/porter-application/'"$collection.return-draft.json" ;;
    after_return_draft)
      $compose run --rm --entrypoint sh harmonicdb-host -c 'test -f /data/porter-application/'"$collection.return-draft.json"
      $compose exec -T harmonicdb-porter sh -c 'test ! -d /ipc/lodgements/lodged || test -z "$(find /ipc/lodgements/lodged -name "LG-*.json" -print -quit)"' ;;
    after_return_lodgement)
      $compose exec -T harmonicdb-porter sh -c 'test -n "$(find /ipc/lodgements/lodged -name "LG-*.json" -print -quit)"' ;;
  esac

  $compose start harmonicdb-host >/dev/null
  if [ "$point" = "after_effect" ]; then
    deadline=10
    while [ "$deadline" -gt 0 ]; do
      if $compose run --rm --entrypoint sh harmonicdb-host -c 'test -f /data/porter-application/'"$collection.ambiguous.json"; then break; fi
      deadline=$((deadline-1));sleep 1
    done
    $compose exec -T find-me-porter grep -q '"knowledge":"REMOTE_ACCEPTANCE_KNOWN"' /ipc/carriage/"$package".json
    $compose exec -T find-me-porter test ! -f /ipc/inbox/"$package".json
    return
  fi
  deadline=30
  while [ "$deadline" -gt 0 ]; do
    if $compose exec -T find-me-porter grep -q RETURN_HELD /ipc/tickets/"$ticket".json; then break; fi
    deadline=$((deadline-1));sleep 1
  done
  $compose run --rm find-me-host -c '
from pathlib import Path
from porter.tickets import collect
t=Path("/ipc/generation6.ticket").read_text();answer=collect("/ipc",t)
assert answer["package"]["payload"]["envelope"]["protocol"]=="HDBE/1",answer
'
}

for point in after_read after_effect after_application_record after_return_draft after_return_lodgement; do run_case "$point"; done
echo "PORTER Generation VI: five post-Collection application realities produced no honest DS fact; Return lodgement remained correspondence, and the ambiguous HDBE effect stayed application-owned."
