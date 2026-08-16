#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
compose="docker compose -f compose.generation1.yaml"
$compose down -v --remove-orphans >/dev/null 2>&1 || true
trap '$compose down -v --remove-orphans >/dev/null 2>&1' EXIT
$compose build >/dev/null
$compose up -d sender-porter recipient-porter
$compose run --rm ticket-sender-host
ticket="$($compose exec -T sender-porter cat /ipc/generation2.ticket)"
$compose exec -T sender-porter test -f /ipc/tickets/"$ticket".json
test "$($compose ps --status running --services ticket-sender-host)" = ""
deadline=20
while [ "$deadline" -gt 0 ]; do
  package="$($compose exec -T sender-porter sh -c 'cat /ipc/tickets/by-package/PKG-* 2>/dev/null' || true)"
  if [ -n "$package" ] && $compose exec -T recipient-porter sh -c 'test -n "$(find /ipc/inbox -name "PKG-*.json" -print -quit)"'; then break; fi
  deadline=$((deadline-1));sleep 1
done
$compose run --rm recipient-host
deadline=20
while [ "$deadline" -gt 0 ]; do
  if $compose exec -T sender-porter grep -q RETURN_HELD /ipc/tickets/"$ticket".json; then break; fi
  deadline=$((deadline-1));sleep 1
done
$compose exec -T sender-porter grep -q RETURN_HELD /ipc/tickets/"$ticket".json
test "$($compose ps --status running --services ticket-collector-host)" = ""
$compose restart sender-porter >/dev/null
$compose run --rm ticket-collector-host
$compose exec -T sender-porter grep -q COLLECTED /ipc/generation2.collected
echo "PORTER Generation II: durable Ticket outlived Host and Porter; Return arrived in silence; restarted Host inspected and collected it."
