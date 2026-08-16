"""depdiff CLI — compare dependency locks across refs, classify risk, exit codes.

Exit codes: 0 clean report, 1 warnings only, 2 blocking findings, 3 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import diff_snapshots
from .errors import DepDiffError, GitRefError, ParseError, UnsupportedFormatError
from .git import file_at_head, file_at_ref, resolve_repo
from .models import Dependency, DiffReport
from .parsers import detect_filename, parse_lockfile


def _resolve_source(repo: str, source: str) -> tuple[str, str]:
    """Return (label, content) for a file-or-ref source.
    A source is either ``path/to/lockfile`` (working-tree file) or
    ``ref:path/to/lockfile`` (git object at a ref).
    """
    if os.path.isabs(source) and os.path.isfile(source) and ":" not in source:
        return os.path.basename(source), _read_file(source)
    head_label, head_content = str(source), file_at_head(repo, source)
    if ":" in source and not source.endswith(":") and head_content is None:
        ref, _, file_path = source.partition(":")
        return file_path, file_at_ref(repo, ref, file_path)
    assert head_content is not None
    return head_label, head_content


def _both_absolute_files(a: str, b: str) -> bool:
    return (
        os.path.isabs(a)
        and os.path.isfile(a)
        and ":" not in a
        and os.path.isabs(b)
        and os.path.isfile(b)
        and ":" not in b
    )


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _dep(d: Dependency | None) -> dict[str, object] | None:
    if d is None:
        return None
    return {"version": d.version, "license": sorted(d.license_ids)}


def _report_to_dict(report: DiffReport) -> dict[str, object]:
    return {
        "tool": "depdiff",
        "version": "1.0.0",
        "old": {"source": report.old_source, "format": report.old_format},
        "new": {"source": report.new_source, "format": report.new_format},
        "summary": {
            "total": len(report.changes),
            "added": sum(1 for c in report.changes if c.kind.value == "added"),
            "removed": sum(1 for c in report.changes if c.kind.value == "removed"),
            "upgraded": sum(1 for c in report.changes if c.kind.value == "upgraded"),
            "downgraded": sum(1 for c in report.changes if c.kind.value == "downgraded"),
            "relicensed": sum(1 for c in report.changes if c.kind.value == "relicensed"),
            "blocked": len(report.blocked),
            "warned": len(report.warned),
        },
        "changes": [
            {
                "kind": c.kind.value,
                "name": c.name,
                "old": _dep(c.old),
                "new": _dep(c.new),
                "risk": c.risk.value,
                "reason": c.reason,
            }
            for c in report.changes
        ],
    }


def _format_text(report: DiffReport) -> str:
    lines = [
        f"depdiff: {report.old_source} → {report.new_source}",
        f"formats: {report.old_format} / {report.new_format}",
        f"changes: {len(report.changes)}  blocked: {len(report.blocked)}"
        f"  warned: {len(report.warned)}",
        "",
    ]
    for change in report.changes:
        marker = {"block": "!!", "warn": "! ", "safe": "  "}[change.risk.value]
        old_v = change.old.version if change.old else "-"
        new_v = change.new.version if change.new else "-"
        lines.append(
            f"[{marker}] {change.kind.value:>10} {change.name} ({old_v} → {new_v}) "
            f"risk={change.risk.value} {change.reason}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="depdiff",
        description="Compare dependency lock files across git refs and classify license risk.",
    )
    parser.add_argument("repo", help="absolute path to a git repository")
    parser.add_argument(
        "old_source",
        help="working-tree file path, or ref:path (e.g. main:package-lock.json)",
    )
    parser.add_argument(
        "new_source",
        help="working-tree file path, or ref:path",
    )
    parser.add_argument("-o", "--out", help="write JSON report to file")
    parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        repo = resolve_repo(args.repo)
    except GitRefError as exc:
        # Both sources are absolute existing files → repo is not needed.
        if not _both_absolute_files(args.old_source, args.new_source):
            print(f"depdiff: {exc}", file=sys.stderr)
            return 3
        repo = ""

    try:
        old_label, old_text = _resolve_source(repo, args.old_source)
        new_label, new_text = _resolve_source(repo, args.new_source)
    except (GitRefError, DepDiffError) as exc:
        print(f"depdiff: {exc}", file=sys.stderr)
        return 3

    if not detect_filename(old_label) or not detect_filename(new_label):
        print(
            "depdiff: unsupported lock file name",
            "(expected package-lock.json, poetry.lock, Cargo.lock, requirements*.txt)",
            file=sys.stderr,
        )
        return 3

    try:
        old_snapshot = parse_lockfile(old_text, old_label)
    except (ParseError, UnsupportedFormatError) as exc:
        print(f"depdiff: old snapshot: {exc}", file=sys.stderr)
        return 3
    try:
        new_snapshot = parse_lockfile(new_text, new_label)
    except (ParseError, UnsupportedFormatError) as exc:
        print(f"depdiff: new snapshot: {exc}", file=sys.stderr)
        return 3

    report = diff_snapshots(old_snapshot, new_snapshot, old_source=old_label, new_source=new_label)

    if args.output_format == "json":
        payload = json.dumps(_report_to_dict(report), indent=2, ensure_ascii=False)
        print(payload)
        if args.out:
            Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(_format_text(report))
        if args.out:
            Path(args.out).write_text(
                json.dumps(_report_to_dict(report), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    if report.blocked:
        return 2
    if report.warned:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
