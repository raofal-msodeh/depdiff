"""Diff engine: compare two dependency snapshots and classify every change."""

from __future__ import annotations

from .models import Change, ChangeKind, Dependency, DiffReport, Snapshot
from .policy import classify_change


def _classify_version(old: Dependency, new: Dependency) -> ChangeKind:
    from .semver import Version  # local import to keep import order clean

    try:
        ov, nv = Version(old.version), Version(new.version)
    except ValueError:
        ov, nv = None, None
    if ov is not None and nv is not None:
        if nv > ov:
            return ChangeKind.UPGRADED
        if nv < ov:
            return ChangeKind.DOWNGRADED
    return ChangeKind.RELICENSED if old.license_key() != new.license_key() else ChangeKind.UPGRADED


def diff_snapshots(old: Snapshot, new: Snapshot, *, old_source: str, new_source: str) -> DiffReport:
    """Classify the differences between two snapshots.

    Priority when both version and license change: version direction wins and
    the license change is folded into the risk reason (unless the version is
    identical, in which case the change is RELICENSED).
    """
    report = DiffReport(
        old_format=old.format,
        new_format=new.format,
        old_source=old_source,
        new_source=new_source,
    )
    all_names = sorted(set(old.dependencies) | set(new.dependencies))
    for name in all_names:
        before = old.dependencies.get(name)
        after = new.dependencies.get(name)
        if before is None:
            change = classify_change(Change(kind=ChangeKind.ADDED, name=name, new=after))
        elif after is None:
            change = classify_change(Change(kind=ChangeKind.REMOVED, name=name, old=before))
        elif before.version != after.version:
            kind = _classify_version(before, after)
            change = classify_change(Change(kind=kind, name=name, old=before, new=after))
        elif before.license_key() != after.license_key():
            change = classify_change(
                Change(kind=ChangeKind.RELICENSED, name=name, old=before, new=after)
            )
        else:
            continue  # byte-identical pin and license
        report.changes.append(change)
    return report
