"""Lock-file parsers for the supported subset of formats.

Supported formats (detected, never assumed from extension):
- npm package-lock.json (lockfileVersion >= 2/3 with "packages")
- poetry.lock (TOML, [[package]] entries, both 1.1 legacy and 2.0/2.1 styles)
- Cargo.lock (TOML [[package]] entries, v3/v4)
- requirements.txt (pinned ``name==version`` lines, ``--hash`` and comments allowed)

All parsers are pure parsing: no registry access, no installation, no network.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .errors import ParseError, UnsupportedFormatError
from .models import Dependency, Snapshot

try:
    import tomllib  # Python >= 3.11
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

# SPDX license names (subset relevant for classification); anything not listed
# here is still preserved verbatim and classified as UNKNOWN by the policy layer.
SPDX_IDS: frozenset[str] = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Unlicense",
        "CC0-1.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "MPL-2.0",
        "PSF-2.0",
        "Artistic-2.0",
        "Zlib",
        "BlueOak-1.0.0",
        "BSL-1.0",
        "ECL-2.0",
        "WTFPL",
        "Public Domain",
        "UNKNOWN",
    }
)

LICENSE_NAME_MAP: dict[str, str] = {
    "MIT License": "MIT",
    "The MIT License": "MIT",
    "MIT license": "MIT",
    "Apache Software License": "Apache-2.0",
    "Apache License 2.0": "Apache-2.0",
    "Apache License, Version 2.0": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "BSD-3-Clause": "BSD-3-Clause",
    "ISC License": "ISC",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "The Unlicense": "Unlicense",
}


def _normalize_license(raw: str) -> str:
    raw = raw.strip()
    if raw in SPDX_IDS:
        return raw
    mapped = LICENSE_NAME_MAP.get(raw)
    if mapped:
        return mapped
    return raw


def _extract_license_ids(value: Any) -> tuple[str, ...]:
    """Turn a license field (string, list, or object) into normalized IDs."""
    if isinstance(value, dict):
        text = value.get("text") or value.get("license") or ""
        return (_normalize_license(str(text)),) if text else ()
    if isinstance(value, str):
        return (_normalize_license(value),) if value else ()
    if isinstance(value, list):
        ids: list[str] = []
        for item in value:
            if isinstance(item, dict):
                ids.append(_normalize_license(str(item.get("text", ""))))
            else:
                ids.append(_normalize_license(str(item)))
        return tuple(i for i in ids if i)
    return ()


def _norm_name(name: str) -> str:
    base = name.split("[")[0]
    return re.sub(r"[-_.]+", "-", base).lower()


# ---------------------------------------------------------------------------
# npm package-lock.json (lockfileVersion 2/3)
# ---------------------------------------------------------------------------

_NPM_RE = re.compile(r"^package-lock\.json$")


def _try_npm(text: str) -> Snapshot | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    lockfile_version = data.get("lockfileVersion")
    if lockfile_version in (0, 1):
        raise UnsupportedFormatError(
            "package-lock.json v1 is not supported; regenerate with npm >=7 (lockfileVersion 2/3)"
        )
    if lockfile_version not in (2, 3):
        return None
    packages = data.get("packages")
    if not isinstance(packages, dict):
        return None
    deps: dict[str, Dependency] = {}
    for key, entry in packages.items():
        if not isinstance(entry, dict):
            return None
        if not key:
            continue
        if not key.startswith("node_modules/"):
            continue
        relative = key[len("node_modules/") :]
        # hoisted / nested: use the last path segment (most specific install)
        name = relative.rsplit("node_modules/", 1)[-1]
        if not name:
            return None
        version = str(entry.get("version", ""))
        if not re.match(r"^\d+(\.\d+)*(-[A-Za-z0-9.+-]+)?$", version):
            continue  # hoisted / synthetic entry without a real pin
        ids = _extract_license_ids(entry.get("license"))
        norm = _norm_name(name)
        existing = deps.get(norm)
        if existing is None or existing.version != version:
            deps[norm] = Dependency(norm, version, ids)
    if not deps:
        return None
    return Snapshot("npm-lock3", deps)


# ---------------------------------------------------------------------------
# poetry.lock (TOML)
# ---------------------------------------------------------------------------

_POETRY_RE = re.compile(r"^poetry\.lock$")


def _try_poetry(text: str) -> Snapshot | None:
    try:
        data = tomllib.loads(text)
    except Exception:  # invalid TOML
        return None
    if not isinstance(data, dict):
        return None
    # 1.1 legacy: toml metadata header block; 2.x: same [[package]] shape
    packages = data.get("package")
    if not isinstance(packages, list):
        return None
    if not all(isinstance(p, dict) and "name" in p and "version" in p for p in packages):
        return None
    deps: dict[str, Dependency] = {}
    for entry in packages:
        name = _norm_name(str(entry["name"]))
        version = str(entry["version"])
        ids = _extract_license_ids(entry.get("category"))
        # poetry license field
        lic = entry.get("optional")
        lic = entry.get("license") or lic
        lic_ids = _extract_license_ids(lic)
        if not lic_ids:
            lic_ids = ids
        deps[name] = Dependency(name, version, lic_ids)
    return Snapshot("poetry", deps)


# ---------------------------------------------------------------------------
# Cargo.lock (TOML)
# ---------------------------------------------------------------------------

_CARGO_RE = re.compile(r"^Cargo\.lock$")


def _try_cargo(text: str) -> Snapshot | None:
    try:
        data = tomllib.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("package"), list):
        return None
    packages: list[dict[str, Any]] = data["package"]
    if not packages:
        return None
    for entry in packages:
        if not isinstance(entry, dict) or "name" not in entry or "version" not in entry:
            return None
    deps: dict[str, Dependency] = {}
    for entry in packages:
        name = _norm_name(str(entry["name"]))
        version = str(entry["version"])
        ids = _extract_license_ids(entry.get("license"))
        existing = deps.get(name)
        # Cargo can list the same crate multiple times (distinct sources);
        # keep the entry with the declared license if any.
        if existing is None or (not existing.license_ids and ids):
            deps[name] = Dependency(name, version, ids)
    return Snapshot("cargo", deps)


# ---------------------------------------------------------------------------
# requirements.txt (pinned)
# ---------------------------------------------------------------------------

_REQ_RE = re.compile(r"^requirements(-[A-Za-z0-9_.-]+)?\.txt$")
_REQ_NAME = r"([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?(?:\[[A-Za-z0-9_., -]+\])?)"


def _make_req_line() -> re.Pattern[str]:
    return re.compile(
        "^"
        + _REQ_NAME
        + r"==([A-Za-z0-9._*+!-]+)(?:[ \t]*(?:--hash[^\n]*|[#][^\n]*|[;][^\n]*)?)?[ \t]*\\?\s*$"
    )


_REQ_LINE = _make_req_line()

_REQ_SKIP = re.compile(r"^(\s*$|[#@-]|-[a-z])")


def _try_requirements(text: str) -> Snapshot | None:
    deps: dict[str, Dependency] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _REQ_SKIP.match(line):
            continue
        if line.startswith("-"):
            continue
        match = _REQ_LINE.match(line)
        if match is None:
            return None  # unparsable requirement → reject whole file
        name, version = match.group(1), match.group(3)
        deps[_norm_name(name)] = Dependency(_norm_name(name), version, ())
    if not deps:
        return None
    return Snapshot("requirements", deps)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_PARSERS = [_try_npm, _try_poetry, _try_cargo, _try_requirements]


def detect_filename(filename: str) -> bool:
    """Whether the basename looks like a supported lock file."""
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return bool(
        _NPM_RE.match(base)
        or _POETRY_RE.match(base)
        or _CARGO_RE.match(base)
        or _REQ_RE.match(base)
    )


def parse_lockfile(text: str, filename: str = "") -> Snapshot:
    """Parse ``text`` as any supported lock format; raise on failure."""
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Order: try the parser matching the filename first, then all others.
    ordered = list(_PARSERS)
    if _NPM_RE.match(base):
        ordered = [_try_npm, *_PARSERS]
    elif _POETRY_RE.match(base):
        ordered = [_try_poetry, *_PARSERS]
    elif _CARGO_RE.match(base):
        ordered = [_try_cargo, *_PARSERS]
    elif _REQ_RE.match(base):
        ordered = [_try_requirements, *_PARSERS]
    tried: list[str] = []
    format_specific = (
        _try_npm
        if _NPM_RE.match(base)
        else _try_poetry
        if _POETRY_RE.match(base)
        else _try_cargo
        if _CARGO_RE.match(base)
        else _try_requirements
        if _REQ_RE.match(base)
        else None
    )
    for parser in ordered:
        snapshot = parser(text)
        if snapshot is not None:
            return snapshot
        tried.append(parser.__name__)
    # A filename matching a known format that fails to parse is a corruption
    # problem; an unrecognized file is simply unsupported.
    if format_specific is not None:
        raise ParseError(
            f"{base!r} failed to parse as {format_specific.__name__[6:]} (tried {', '.join(tried)})"
        )
    raise UnsupportedFormatError(
        f"file has no supported lock format: {base!r} (tried {', '.join(tried)})"
    )
