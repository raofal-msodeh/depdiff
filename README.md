# DepDiff

**Compare dependency lock files across git refs and classify every change with a license-risk verdict — zero install, offline, zero runtime dependencies.**

```
depdiff <repo> main:package-lock.json feature-x:package-lock.json
depdiff <repo> HEAD~5:poetry.lock HEAD:poetry.lock --format json -o report.json
depdiff <repo> base/requirements.txt feature/requirements.txt
```

Exit codes: `0` clean report, `1` warnings only, `2` blocking findings, `3` usage error.

![License](https://img.shields.io/github/license/raofal-msodeh/depdiff)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Tests](https://img.shields.io/badge/tests-40%20passing-green)
![Size](https://img.shields.io/badge/wheel-16%20KB-lightgrey)

## Why this exists

Dependency **lock drift** between branches is a real, under-served problem. When a long-lived branch diverges from `main`, its lock file quietly accumulates dependency additions, version jumps, and — worst of all — license transitions that nobody reviews. By the time the branch merges, a GPL-licensed transitive dependency can land in a proprietary codebase with no traceable decision. Existing tools either scan a *single* snapshot (license checkers) or show raw diffs (`git diff -- package-lock.json`) with no semantic understanding and no risk classification. [Lock-file drift is documented as a recurring supply-chain hygiene issue][1] [2], and the gap this tool fills is the **diff between two lock states with a per-change verdict**.

What makes DepDiff different:

| Capability | `git diff` | License checkers | **DepDiff** |
|---|---|---|---|
| Semantic diff across git refs | ❌ raw text | ❌ single snapshot | ✅ |
| Per-change license risk verdict | ❌ | ⚠️ whole-snapshot | ✅ per dependency |
| Understands major-version jumps | ❌ | ❌ | ✅ semver-aware |
| Detects re-licensing of existing deps | ❌ | ❌ | ✅ |
| Offline / no network | ✅ | varies | ✅ |
| Zero runtime dependencies | ✅ | rarely | ✅ |
| Supported formats | — | many | npm (v2/3), poetry, Cargo, requirements |

## Install

```bash
pip install depdiff                 # or:
pipx install depdiff                # or use the pre-built wheel from releases
```

Python 3.11+ only. No other packages are required at runtime — parsing is done with the standard library (including `tomllib`).

## Usage

The command takes a git repository path and two sources. A source is either a working-tree file or a `ref:path` expression read from git history (no checkout needed):

```bash
# Compare main against a feature branch without checking anything out
depdiff /path/to/repo main:package-lock.json feature/payments:package-lock.json

# Last week's snapshot versus now (poetry)
depdiff /path/to/repo "@{7 days ago}:poetry.lock" HEAD:poetry.lock

# Two working-tree files from unrelated locations
depdiff /path/to/repo /tmp/audit/Cargo.lock /tmp/audit-new/Cargo.lock

# JSON report for CI gating
depdiff /path/to/repo main:package-lock.json HEAD:package-lock.json \
  --format json -o depdiff-report.json
echo $?   # 2 → pipeline fails (blocked)
```

### Exit codes (CI gating)

| Code | Meaning |
|---|---|
| 0 | No changes, or all changes are low-risk (permissive licenses) |
| 1 | Only warnings (major jumps, weak-copyleft additions, license downgrades) |
| 2 | At least one **blocked** change (new unknown-license dep, GPL/AGPL addition, strict re-license) |
| 3 | Usage error (bad repo, invalid ref, unsupported file, corrupt lock) |

### JSON output

```json
{
  "tool": "depdiff",
  "version": "1.0.0",
  "old": {"source": "package-lock.json", "format": "npm-lock3"},
  "new": {"source": "package-lock.json", "format": "npm-lock3"},
  "summary": {"total": 3, "added": 2, "removed": 0, "upgraded": 1,
              "downgraded": 0, "relicensed": 0, "blocked": 1, "warned": 1},
  "changes": [
    {"kind": "added", "name": "agpl-lib", "old": null,
     "new": {"version": "0.1.0", "license": ["AGPL-3.0-only"]},
     "risk": "block", "reason": "new strong-copyleft dependency (GPL/AGPL)"}
  ]
}
```

## Change kinds and risk policy

Every diff entry is classified into exactly one **change kind**: `added`, `removed`, `upgraded`, `downgraded`, or `relicensed`. The risk verdict is computed per change, not per dependency, because risk is introduced by *transitions*:

| Change | Verdict |
|---|---|
| Added permissive license | safe |
| Added unknown license (format declares licenses) | **block** |
| Added unknown license (`requirements.txt` declares none) | warn |
| Added strong copyleft (GPL/AGPL) | **block** |
| Added weak copyleft (LGPL/MPL) | warn |
| Removed | safe (risk reduced) |
| Upgraded with major version jump | warn |
| License moved to a stricter class | block/warn by class |
| License downgraded | warn |

The built-in license table covers SPDX identifiers for permissive (MIT, Apache-2.0, BSD-*, ISC, Unlicense, CC0, PSF, BlueOak…), weak copyleft (LGPL-*, MPL-2.0) and strong copyleft (GPL-*, AGPL-*).

## Supported lock formats

| Format | File pattern | License metadata |
|---|---|---|
| npm (lockfileVersion 2/3) | `package-lock.json` | yes |
| Poetry | `poetry.lock` | yes |
| Cargo | `Cargo.lock` | yes |
| pip | `requirements*.txt` | no (adds are warn, never block, for that reason) |

## Examples

A full worked example, including a simulated cross-branch drift, lives in [`examples/`](examples/). Quick taste:

```bash
$ depdiff myapp main:package-lock.json staging:package-lock.json
depdiff: package-lock.json → package-lock.json
formats: npm-lock3 / npm-lock3
changes: 4  blocked: 1  warned: 1

[  ]     removed lodash      (4.17.21 → -) risk=safe dependency removed; risk reduced
[!]  upgraded express      (4.18.2 → 5.0.0) risk=warn major version change 4.18.2→5.0.0
[  ]     added  qs          (6.11.0) risk=safe new dependency with permissive license
[!!]     added  copyleft-lib (0.2.0) risk=block new strong-copyleft dependency (GPL/AGPL)
```

## Library API

```python
from depdiff.parsers import parse_lockfile
from depdiff.engine import diff_snapshots
from depdiff.policy import classify_change

old = parse_lockfile(open("old-lock.json").read(), "package-lock.json")
new = parse_lockfile(open("new-lock.json").read(), "package-lock.json")
report = diff_snapshots(old, new, old_source="old-lock.json", new_source="new-lock.json")
for change in report.changes:
    classified = classify_change(change)
    print(classified.name, classified.risk.value, classified.reason)
```

## Project quality

The project ships with **40 passing tests** (unit tests for parsers, semver, policy, git integration and the full CLI flow), type checks with `mypy --strict`, and lint/format via `ruff`. The [`scripts/red_team.sh`](scripts/red_team.sh) harness exercises 13 hostile scenarios — path traversal in refs, invalid refs, missing files at valid refs, corrupted JSON, unsupported filenames, npm v1 rejection, empty files, and non-git directories — all passing. See [`docs/release-audit.md`](docs/release-audit.md) for the pre-release checklist and [`docs/discovery-notes.md`](docs/discovery-notes.md) for the problem research.

## Architecture

Seven modules, no dependencies: `models` (typed value objects), `errors` (four exception types), `parsers` (format dispatch + per-format parsers), `semver` (pure parser + major-jump detection), `policy` (risk classification), `git` (read-only refs via `git show`), `engine` (diff orchestration), and `cli`. Decisions are recorded in [`docs/adr/0001-foundation.md`](docs/adr/0001-foundation.md).

## License

MIT — see [`LICENSE`](LICENSE).

## References

[1]: https://sbomify.com/2024/07/30/what-is-lock-file-drift/ "What is lock file drift? — sbomify"
[2]: https://docs.npmjs.com/cli/v9/configuring-npm/package-lock-json "package-lock.json specification — npm docs"
