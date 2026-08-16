# ADR 0001: Foundation — A Lock-File Diff and License-Risk CLI

## Status

Accepted — 2026-08-16

## Context

Long-lived branches drift away from `main`, and their dependency lock files accumulate additions, version jumps, and license transitions that no one reviews before merge. Existing tooling splits into two camps: whole-snapshot license scanners that cannot express a *diff*, and raw `git diff` that cannot interpret lock files semantically. A dedicated, offline tool that reads lock files at arbitrary refs and emits a per-change risk verdict fills a documented hygiene gap while remaining small enough to vendor into CI.

## Decision

Build `depdiff` as a pure-Python CLI (3.11+) with zero runtime dependencies:

- **Read-only git access.** Lock files are read from git objects via `git show <ref>:<path>`; no checkout, no network, no mutation of the target repository.
- **Four parsers** (npm lockfile v2/3, Poetry, Cargo, `requirements*.txt`) behind a filename-dispatching facade; unsupported filenames and lockfile v1 are rejected loudly.
- **Change kinds** (`added`/`removed`/`upgraded`/`downgraded`/`relicensed`) computed by matching packages by normalized name, with a hand-rolled semver parser (no dependency) that also detects major jumps and orders pre/post releases.
- **Risk verdicts per change** (`safe`/`warn`/`block`) from a small SPDX-class table; formats that cannot declare licenses (`requirements.txt`) degrade to `warn` rather than blocking on absence of metadata.
- **Exit codes 0/1/2/3** so CI pipelines can gate merges directly.

## Consequences

- Security surface is limited: ref paths reject traversal (`..`, absolute paths), and all git calls go through a subprocess helper without shell expansion.
- The SPDX table is intentionally small and extendable; unrecognized identifiers become `unknown` (blocking when added in license-declaring formats).
- No external HTTP means the tool never observes package registries; license signals are exactly what lock files carry.
- Python-only typing is validated with `mypy --strict`, lint/format with `ruff`, and hostile inputs are exercised by `scripts/red_team.sh`.
