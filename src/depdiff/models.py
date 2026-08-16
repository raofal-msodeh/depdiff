"""Core data models for DepDiff.

A ``Dependency`` is one entry parsed from a lock file: a fully-qualified name,
exact version, and optional declared license identifiers (SPDX expressions are
simplified to their leaf identifiers).
"""

from __future__ import annotations

import dataclasses
from enum import Enum


class ChangeKind(str, Enum):  # noqa: UP042
    """Direction of a dependency change between two snapshots."""

    ADDED = "added"
    REMOVED = "removed"
    UPGRADED = "upgraded"
    DOWNGRADED = "downgraded"
    RELICENSED = "relicensed"


class RiskLevel(str, Enum):  # noqa: UP042
    """License-risk verdict for a single dependency change."""

    SAFE = "safe"  # no new risk introduced
    WARN = "warn"  # potentially problematic (e.g., changed license, major jump)
    BLOCK = "block"  # policy violation (copyleft introduction, unknown license)


@dataclasses.dataclass(frozen=True)
class Dependency:
    """One pinned dependency from a parsed lock file."""

    name: str  # normalized package name
    version: str  # exact pinned version
    license_ids: tuple[str, ...] = ()  # empty when the lock entry declares none

    def license_key(self) -> str:
        return ",".join(sorted(self.license_ids))


@dataclasses.dataclass(frozen=True)
class Change:
    """A classified difference between the old and new snapshots."""

    kind: ChangeKind
    name: str
    old: Dependency | None = None
    new: Dependency | None = None
    risk: RiskLevel = RiskLevel.SAFE
    reason: str = ""


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """A parsed lock file."""

    format: str  # npm-lock3 | poetry | cargo | requirements
    dependencies: dict[str, Dependency]


@dataclasses.dataclass
class DiffReport:
    """The full comparison result."""

    old_format: str
    new_format: str
    old_source: str
    new_source: str
    changes: list[Change] = dataclasses.field(default_factory=list)

    @property
    def blocked(self) -> list[Change]:
        return [c for c in self.changes if c.risk == RiskLevel.BLOCK]

    @property
    def warned(self) -> list[Change]:
        return [c for c in self.changes if c.risk == RiskLevel.WARN]
