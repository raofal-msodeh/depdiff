#!/usr/bin/env bash
# DepDiff red-team: hostile inputs against a fixture repository.
set -u
TMPDIR_WORK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_WORK"' EXIT
PASS=0
FAIL=0
PYTHON="${PYTHON:-python3}"
expect() {
  local label="$1"
  local want="$2"
  local got="$3"
  if [ "$want" = "$got" ]; then
    PASS=$((PASS + 1))
    echo "PASS  $label (exit=$got)"
  else
    FAIL=$((FAIL + 1))
    echo "FAIL  $label (want=$want got=$got)"
  fi
}
depdiff_cli() {
  "$PYTHON" -m depdiff.cli "$@" > /dev/null 2> "$TMPDIR_WORK/err"
  local rc=$?
  echo "$rc"
}
# Fixture repository: two commits with lock files that drift.
mkdir -p "$TMPDIR_WORK/repo"
cd "$TMPDIR_WORK/repo"
git init -q -b main
git config user.name "Ada Lovelace"
git config user.email "ada@example.com"
cat > package-lock.json << 'LOCKEOF'
{
  "name": "r",
  "lockfileVersion": 3,
  "packages": {
    "": {"name": "r"},
    "node_modules/safe": {"version": "1.0.0", "license": "MIT"}
  }
}
LOCKEOF
git add -A && git commit -q -m "initial"
cat > package-lock.json << 'LOCKEOF'
{
  "name": "r",
  "lockfileVersion": 3,
  "packages": {
    "": {"name": "r"},
    "node_modules/safe": {"version": "1.0.0", "license": "MIT"},
    "node_modules/evil": {"version": "0.1.0", "license": "AGPL-3.0-only"}
  }
}
LOCKEOF
git add -A && git commit -q -m "add evil dep"

echo "== red-team scenarios =="

# 1. non-git directory
mkdir -p "$TMPDIR_WORK/non-git" && cd "$TMPDIR_WORK/non-git"
expect "plain dir (no .git)" 3 "$(depdiff_cli "$TMPDIR_WORK/non-git" a b)"

# 2. relative repo path
cd "$TMPDIR_WORK"
expect "relative repo path" 3 "$(depdiff_cli "./non-git" a b)"

# 3. path traversal in ref file
cd "$TMPDIR_WORK/repo"
expect "ref path .." 3 "$(depdiff_cli "$TMPDIR_WORK/repo" "HEAD:../etc/passwd" "HEAD:../etc/passwd")"

# 4. absolute ref path
expect "ref path absolute" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" "HEAD:/etc/passwd" "HEAD:/etc/passwd")"

# 5. invalid ref
expect "invalid ref" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" "deadbeef:package-lock.json" "HEAD:package-lock.json")"

# 6. missing file at valid ref
expect "missing file at ref" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" "HEAD:missing.lock" "HEAD:package-lock.json")"

# 7. corrupted JSON lock
printf '{"name": "r", "lockfileVersion": 3, "packages": {"' > /tmp/corrupt-lock.json
expect "corrupt JSON lock" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" /tmp/corrupt-lock.json /tmp/corrupt-lock.json)"

# 8. unsupported filename
expect "unsupported filename" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" "HEAD:README.md" "HEAD:README.md")"

# 9. lockfile v1 rejected
cat > /tmp/v1-lock.json << 'LOCKEOF'
{"name": "r", "lockfileVersion": 1, "dependencies": {"x": {"version": "1.0.0"}}}
LOCKEOF
expect "npm lockfile v1" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" /tmp/v1-lock.json /tmp/v1-lock.json)"

# 10. empty file
: > /tmp/empty.json
expect "empty lock file" 3 "$(depdiff_cli "$TMPDIR_WORK/repo" /tmp/empty.json /tmp/empty.json)"

# 11. clean drift comparison (exit 2 = blocked by AGPL)
expect "blocked drift comparison" 2 "$(depdiff_cli "$TMPDIR_WORK/repo" "HEAD~1:package-lock.json" "HEAD:package-lock.json")"

# 12. warning diff: add LGPL via an edited file copy in the repo itself
mkdir -p "$TMPDIR_WORK/repo/warn"
sed 's/"MIT"/"LGPL-3.0-only"/' "$TMPDIR_WORK/repo/package-lock.json" > "$TMPDIR_WORK/repo/warn/package-lock.json"
mkdir -p /tmp/depdiff-warn-old
mkdir -p /tmp/depdiff-warn-new
cp "$TMPDIR_WORK/repo/package-lock.json" /tmp/depdiff-warn-old/package-lock.json
cp "$TMPDIR_WORK/repo/warn/package-lock.json" /tmp/depdiff-warn-new/package-lock.json
expect "warn drift comparison" 1 "$(depdiff_cli "$TMPDIR_WORK/repo" /tmp/depdiff-warn-old/package-lock.json /tmp/depdiff-warn-new/package-lock.json)"

# 13. clean (safe) diff
mkdir -p /tmp/clean
mkdir -p /tmp/clean-new-dir
cat > /tmp/clean/package-lock.json << 'LOCKEOF'
{"name":"r","lockfileVersion":3,"packages":{"":{"name":"r"},"node_modules/a":{"version":"1.0.0","license":"MIT"}}}
LOCKEOF
cat > /tmp/clean-new-dir/package-lock.json << 'LOCKEOF'
{"name":"r","lockfileVersion":3,"packages":{"":{"name":"r"},"node_modules/a":{"version":"1.0.1","license":"MIT"}}}
LOCKEOF
expect "safe drift comparison" 0 "$(depdiff_cli "$TMPDIR_WORK/repo" /tmp/clean/package-lock.json /tmp/clean-new-dir/package-lock.json)"

echo ""
echo "red-team results: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
