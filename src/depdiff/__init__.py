"""DepDiff — compare dependency lock files across git refs, offline.

Public API:

    from depdiff.parsers import parse_lockfile
    from depdiff.engine import diff_snapshots

    old = parse_lockfile(open("a/package-lock.json").read(), "package-lock.json")
    new = parse_lockfile(open("b/package-lock.json").read(), "package-lock.json")
    report = diff_snapshots(old, new, old_source="main", new_source="feature")
"""

__version__ = "1.0.0"
