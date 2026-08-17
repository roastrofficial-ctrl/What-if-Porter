#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
docker compose config --format json | python3 -c '
import json,sys
services=json.load(sys.stdin)["services"]
for name in ("porter-find-me","porter-harmonicdb"):
    command=" ".join(services[name]["command"])
    assert "--native-listen" in command
    assert "http://" not in command and "https://" not in command
    assert "--routes" not in command and "--listen" not in command
assert services["harmonicdb"]["network_mode"]=="none"
'
for name in butterfly-porter-find-me-1 butterfly-porter-harmonicdb-1; do
  test "$(docker inspect -f '{{json .Config.ExposedPorts}}' "$name")" = "null"
  docker exec "$name" python -c 'import socket; s=socket.socket(); s.settimeout(.2); assert s.connect_ex(("127.0.0.1",7070)) != 0'
done
echo "PORTER 1.4 Butterfly: native carriage active; HTTP carriage absent; HarmonicDB networkless."
