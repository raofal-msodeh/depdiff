# Release audit — depdiff 0.1.0
- Quality gate: ruff check/format, mypy --strict, 45 pytest tests, python -m build — all green.
- Red team: scripts/red_team.sh — 8 hostile scenarios all rejected safely.
- Zero third-party dependencies; Python >=3.11 stdlib only (tomllib, argparse, json).
- No network calls; no telemetry; no credentials handled beyond pass-through validation.
- Packaging: PEP 621 pyproject.toml, src layout, hatch-style wheel builds cleanly.
