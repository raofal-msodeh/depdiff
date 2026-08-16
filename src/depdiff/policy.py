"""License-risk policy engine.

Classifies a dependency **change** (not just a dependency) because risk is
introduced by transitions: a copyleft dependency that already existed is a
known quantity; a newly added AGPL dependency is a material risk.

Risk classes:
- PERMISSIVE: MIT, Apache-2.0, BSD-*, ISC, 0BSD, Unlicense, CC0-1.0, PSF-2.0,
  Artistic-2.0, Zlib, BlueOak-1.0.0, BSL-1.0, ECL-2.0, WTFPL
- WEAK_COPYLEFT: LGPL-*, MPL-2.0
- STRONG_COPYLEFT: GPL-*, AGPL-*
- UNKNOWN: anything else, including an empty license set

The policy verdict applies per change kind:
- added: UNKNOWN → block, strong copyleft → block, weak copyleft → warn
- removed: always safe (risk reduced)
- upgraded: major version jump → warn; license change into a stricter class →
  escalate; otherwise safe
- downgraded: license downgrade → warn
- relicensed: stricter class than before → warn/block per class
"""

from __future__ import annotations

from .models import Change, ChangeKind, RiskLevel
from .semver import is_major_jump

PERMISSIVE = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Unlicense",
        "CC0-1.0",
        "PSF-2.0",
        "Artistic-2.0",
        "Zlib",
        "BlueOak-1.0.0",
        "BSL-1.0",
        "ECL-2.0",
        "WTFPL",
        "Public Domain",
        "HPND",
    }
)
WEAK_COPYLEFT = frozenset(
    {"LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "MPL-2.0"}
)
STRONG_COPYLEFT = frozenset(
    {
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
    }
)

_CLASS_ORDER = {"permissive": 0, "weak": 1, "strong": 2, "unknown": 3}


def license_class(lic_ids: tuple[str, ...]) -> str:
    """Strictest class among the declared license ids."""
    if not lic_ids:
        return "unknown"
    best = "permissive"
    for lic in lic_ids:
        if lic in STRONG_COPYLEFT:
            return "strong"
        if lic in WEAK_COPYLEFT:
            best = max(best, "weak", key=lambda c: _CLASS_ORDER[c])
        elif lic not in PERMISSIVE:
            return "unknown"
    return best


def _escalate(change: Change, reason: str, risk: RiskLevel) -> Change:
    """Escalate only if ``risk`` is strictly worse than the current verdict."""
    if risk in (RiskLevel.BLOCK, RiskLevel.WARN) and change.risk in (RiskLevel.SAFE,):
        return Change(
            kind=change.kind,
            name=change.name,
            old=change.old,
            new=change.new,
            risk=risk,
            reason=reason,
        )
    if risk == RiskLevel.BLOCK and change.risk == RiskLevel.WARN:
        return Change(
            kind=change.kind,
            name=change.name,
            old=change.old,
            new=change.new,
            risk=risk,
            reason=reason,
        )
    return change


def _format_declares_licenses(change: Change) -> bool:
    """Whether the lock format declares license metadata at all.

    requirements.txt carries no license info, so an empty license set there is
    expected rather than suspicious.
    """
    return any(dep is not None and dep.license_ids for dep in (change.old, change.new))


def classify_change(change: Change) -> Change:
    """Return ``change`` with ``risk`` and ``reason`` filled in."""
    if change.kind == ChangeKind.REMOVED:
        return Change(
            kind=change.kind,
            name=change.name,
            old=change.old,
            new=change.new,
            risk=RiskLevel.SAFE,
            reason="dependency removed; risk reduced",
        )

    new_lic = change.new.license_ids if change.new else ()
    new_class = license_class(new_lic)

    if change.kind == ChangeKind.ADDED:
        if new_class == "unknown":
            if _format_declares_licenses(change):
                return Change(
                    kind=change.kind,
                    name=change.name,
                    old=change.old,
                    new=change.new,
                    risk=RiskLevel.BLOCK,
                    reason="new dependency with unknown license",
                )
            return Change(
                kind=change.kind,
                name=change.name,
                old=change.old,
                new=change.new,
                risk=RiskLevel.WARN,
                reason="new dependency; license unknown (format declares none)",
            )
        if new_class == "strong":
            return Change(
                kind=change.kind,
                name=change.name,
                old=change.old,
                new=change.new,
                risk=RiskLevel.BLOCK,
                reason="new strong-copyleft dependency (GPL/AGPL)",
            )
        if new_class == "weak":
            return Change(
                kind=change.kind,
                name=change.name,
                old=change.old,
                new=change.new,
                risk=RiskLevel.WARN,
                reason="new weak-copyleft dependency (LGPL/MPL)",
            )
        return Change(
            kind=change.kind,
            name=change.name,
            old=change.old,
            new=change.new,
            risk=RiskLevel.SAFE,
            reason="new dependency with permissive license",
        )

    # version-change kinds: UPGRADED / DOWNGRADED / RELICENSED
    old_class = license_class(change.old.license_ids) if change.old else new_class

    if new_class != old_class:
        if new_class in ("unknown", "strong"):
            verdict = _escalate(
                change, f"license class changed {old_class}→{new_class}", RiskLevel.BLOCK
            )
        else:
            verdict = _escalate(
                change, f"license class changed {old_class}→{new_class}", RiskLevel.WARN
            )
    else:
        verdict = change

    if change.kind in (ChangeKind.UPGRADED, ChangeKind.DOWNGRADED) and change.old and change.new:
        if is_major_jump(change.old.version, change.new.version):
            verdict = _escalate(
                verdict,
                f"major version change {change.old.version}→{change.new.version}",
                RiskLevel.WARN,
            )
    return verdict
