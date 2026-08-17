#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest -v tests.test_introductions
(cd ../passports && node --test test/passport.test.js)
echo "PORTER 1.1 security: adversarial admission and offline Technical Passport claim verification passed."
