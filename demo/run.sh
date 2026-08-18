#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
compose="docker compose -f demo/compose.yaml"

$compose down -v --remove-orphans >/dev/null 2>&1 || true
trap '$compose down -v --remove-orphans >/dev/null 2>&1' EXIT INT TERM

echo "Building the PORTER Public House..."
$compose build
$compose up -d visitor-porter taproom-porter taproom-host

echo "\nThe isolated Visitor Host is lodging an order..."
$compose run --rm visitor-host
