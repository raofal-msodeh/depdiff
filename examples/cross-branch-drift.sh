#!/usr/bin/env bash
# Simulates cross-branch drift: main and a long-lived feature branch
# diverge in their package-lock.json, then depdiff classifies the drift.
set -u
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
mkdir app && cd app
git init -q -b main
git config user.name "A" && git config user.email "a@example.com"

cat > package-lock.json << 'LOCK'
{
  "name": "app",
  "lockfileVersion": 3,
  "packages": {
    "": {"name": "app"},
    "node_modules/express": {"version": "4.18.2", "license": "MIT"},
    "node_modules/lodash": {"version": "4.17.21", "license": "MIT"}
  }
}
LOCK
git add -A && git commit -q -m "initial"
git checkout -q -b feature/payments
sed -i 's/"node_modules\/lodash": {"version": "4.17.21", "license": "MIT"}/"node_modules\/lodash": {"version": "4.17.21", "license": "MIT"},\n    "node_modules\/copyleft-lib": {"version": "0.2.0", "license": "AGPL-3.0-only"},\n    "node_modules\/qs": {"version": "6.11.0", "license": "BSD-3-Clause"}/' package-lock.json
sed -i 's/"version": "4.18.2"/"version": "5.0.0"/' package-lock.json
git add -A && git commit -q -m "feature deps"
git checkout -q main
sed -i 's/"node_modules\/lodash": {"version": "4.17.21", "license": "MIT"}/"node_modules\/lodash": {"version": "4.17.21", "license": "MIT"},\n    "node_modules\/dotenv": {"version": "16.3.1", "license": "BSD-2-Clause"}/' package-lock.json
git add -A && git commit -q -m "main deps"

echo "== depdiff feature/payments vs main =="
python3 -m depdiff.cli "$TMP/app" "feature/payments:package-lock.json" "main:package-lock.json"
echo "== exit code: $? =="
