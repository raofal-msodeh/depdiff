# Changelog

All notable changes to depdiff will be documented in this file.

## [1.0.0] - 2026-08-16

### Added
- Compare dependency lock files across git refs without checkout (`ref:path` syntax).
- Four supported formats: npm package-lock.json (v2/3), poetry.lock, Cargo.lock, requirements*.txt.
- Semantic change kinds: added, removed, upgraded, downgraded, relicensed.
- Per-change license-risk verdicts: safe / warn / block with actionable reasons.
- Semver-aware major version jump detection and pre/post-release ordering.
- Text and JSON report output; JSON report suitable for CI gating.
- Exit codes 0/1/2/3 for clean/warn/blocked/usage-error CI integration.
- Read-only git access (no checkout, no network).
- 40 passing tests, mypy --strict, ruff lint/format, red-team harness (13 hostile scenarios).

### Security
- Ref paths reject `..`, absolute paths, and empty segments.
- File contents read with encoding replacement; no shell injection (no shell=True anywhere).
