# DepDiff Architecture

## Layers
- `schema.py` — strict TOML parser; validates variable names, types, numeric
  bounds, choice lists, regex syntax, when/env expressions, and enforces a
  1 MiB schema cap and a 512-variable cap to bound parsing work.
- `models.py` — frozen dataclasses (`EnvSchema`, `VariableSpec`,
  `VerificationResult`, `VariableResult`). Pure data, no side effects.
- `verify.py` — the pure verification engine. Given a schema, an optional
  environment context, and concrete input values, it returns per-variable
  results (`ok`, `defaulted`, `skipped`, `error`) plus an aggregate error
  count. Side conditions (`when`, `env`) are evaluated against input values.
- `render.py` — writes the final `.env` (with header and timestamp) and the
  `depdiff-manifest.json` provenance artifact. Rejects non-absolute paths and
  non-`.env`/`.txt` output names.
- `cli.py` — argparse CLI (`init`, `verify`, `check`). Maps errors to
  conventional exit codes: 0 pass, 1 verified-fail, 2 input/config error.

## Gate design
`check` re-reads the manifest next to the rendered `.env` and compares
`error_count` against the threshold, giving CI a deterministic gate.

## Red-team surfaces
Relative/escaping output paths, non-.env extensions, malformed .env inputs,
oversized schemas, invalid TOML, unknown environments, invalid when
expressions, and invalid boolean defaults are all explicitly rejected or
reported as errors.
