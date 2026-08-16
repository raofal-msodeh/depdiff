"""Read files from git history without installing dependencies.

All operations shell out to the local ``git`` binary against a local working
tree or refs. No network access, no package managers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .errors import GitRefError


def _git(root: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitRefError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or 'unknown error'}"
        )
    return result.stdout


def resolve_repo(path: str) -> str:
    """Return the absolute repo root for ``path``, raising on failure."""
    if not os.path.isabs(path):
        raise GitRefError(f"repository path must be absolute: {path!r}")
    try:
        root = _git(path, "rev-parse", "--show-toplevel").strip()
    except GitRefError as exc:
        raise GitRefError(f"not a git repository (or any parent): {path!r}") from exc
    return root


def file_at_ref(root: str, ref: str, file_path: str) -> str:
    """Return the text content of ``file_path`` at ``ref`` (git show)."""
    if not file_path or ".." in file_path or file_path.startswith("/"):
        raise GitRefError(f"invalid ref path: {file_path!r}")
    try:
        _git(root, "rev-parse", "--verify", ref)  # validate the ref alone
    except GitRefError as exc:
        raise GitRefError(f"cannot resolve ref {ref!r}") from exc
    try:
        return _git(root, "show", f"{ref}:{file_path}")
    except GitRefError as exc:
        raise GitRefError(f"cannot read {file_path!r} at {ref!r}") from exc


def file_at_head(root: str, file_path: str) -> str | None:
    """Read a file from the working tree; None when missing, raise on traversal."""
    full = (Path(root) / file_path).resolve()
    if not str(full).startswith(os.path.realpath(root)):
        raise GitRefError(f"file escapes repo: {file_path!r}")
    try:
        return full.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def ref_exists(root: str, ref: str) -> bool:
    result = subprocess.run(
        ["git", "-C", root, "rev-parse", "--verify", ref],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0
