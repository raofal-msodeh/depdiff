"""Error taxonomy for DepDiff."""

from __future__ import annotations


class DepDiffError(Exception):
    """Base class for all DepDiff failures."""


class ParseError(DepDiffError):
    """A lock file could not be parsed (unknown format or corrupted content)."""


class UnsupportedFormatError(DepDiffError):
    """The file exists but matches no supported lock format."""


class GitRefError(DepDiffError):
    """A git reference could not be resolved or read."""


class PolicyError(DepDiffError):
    """A user-supplied policy configuration is invalid."""
