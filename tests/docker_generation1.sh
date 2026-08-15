#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
compose="docker compose -f compose.generation1.yaml"
$compose down -v --remove-orphans >/dev/null 2>&1 || true
trap '$compose down -v --remove-orphans >/dev/null 2>&1' EXIT
$compose build >/dev/null
$compose up -d sender-porter recipient-porter
$compose run --rm -d sender-host >/dev/null
deadline=20
while [ "$deadline" -gt 0 ]; do
  package="$($compose exec -T sender-porter cat /ipc/sender.deposited 2>/dev/null || true)"
  if [ -n "$package" ] && $compose exec -T recipient-porter test -f /ipc/inbox/"$package".json; then break; fi
  deadline=$((deadline-1));sleep 1
done
$compose exec -T recipient-porter test -f /ipc/inbox/"$package".json
test "$($compose ps --status running --services recipient-host)" = ""
test "$($compose run --rm sender-host sh -c 'test ! -e /sys/class/net/eth0 && test "$(awk "NR>1{n++}END{print n+0}" /proc/net/route)" -eq 0; echo isolated')" = "isolated"
test "$($compose run --rm recipient-host sh -c 'test ! -e /sys/class/net/eth0 && test "$(awk "NR>1{n++}END{print n+0}" /proc/net/route)" -eq 0; echo isolated')" = "isolated"
$compose run --rm recipient-host
deadline=20
while [ "$deadline" -gt 0 ]; do
  if $compose exec -T sender-porter test -f /ipc/sender.collected-return; then break; fi
  deadline=$((deadline-1));sleep 1
done
$compose exec -T sender-porter test -f /ipc/sender.collected-return
echo "PORTER Generation I: isolated Hosts corresponded; arrival did not invoke recipient Host; Return was explicitly collected."
