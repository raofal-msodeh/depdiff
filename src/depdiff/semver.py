"""Minimal semver helpers — no third-party dependency.

Parses versions like ``1.2.3``, ``1.2.3-beta.1`` and PEP 440 post/dev flavors
that frequently appear in lock files (``1.2.3.post1``, ``1.2.3.dev4``).
Comparison is numeric on (major, minor, patch, pre), where a release beat any
prerelease of the same numbers.
"""

from __future__ import annotations

import re

_PRE = re.compile(
    r"^(\d+(?:\.\d+)*)(?:[._-](alpha|beta|rc|dev|pre|a|b|c)\.?(\d*))?(?:[._-](post|dev)\.?(\d*))?$",
    re.I,
)


class Version:
    __slots__ = ("raw", "numbers", "pre", "post")

    raw: str
    numbers: tuple[int, ...]
    pre: tuple[int, int] | None
    post: int

    def __init__(self, raw: str) -> None:
        self.raw = raw
        match = _PRE.match(raw.strip())
        if match is None:
            raise ValueError(f"not a parseable version: {raw!r}")
        core, pre_name, pre_num, post_name, post_num = match.groups()
        self.numbers = tuple(int(n) for n in core.split("."))
        if pre_name is not None:
            rank = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "dev": -1}[
                pre_name.lower()
            ]
            self.pre = (rank, int(pre_num or 0))
        else:
            self.pre = None
        if post_name is not None:
            self.post = 1 if post_name.lower() == "post" else -1
            self.post = self.post * (int(post_num or 1))
        else:
            self.post = 0

    @property
    def major(self) -> int:
        return self.numbers[0] if self.numbers else 0

    @property
    def minor(self) -> int:
        return self.numbers[1] if len(self.numbers) > 1 else 0

    @property
    def patch(self) -> int:
        return self.numbers[2] if len(self.numbers) > 2 else 0

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None and self.pre[0] >= 0

    def _key(self) -> tuple[tuple[int, ...], tuple[int, ...], int]:
        # release > prerelease of same core; post bumps rank slightly
        if self.pre is None:
            pre_key: tuple[int, ...] = (1,)
        else:
            pre_key = (0, self.pre[0], self.pre[1])
        return (self.numbers, pre_key, self.post)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __le__(self, other: Version) -> bool:
        return self == other or self < other

    def __gt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() > other._key()

    def __ge__(self, other: Version) -> bool:
        return self == other or self > other

    def __repr__(self) -> str:  # pragma: no cover
        return f"Version({self.raw!r})"


def is_major_jump(old: str, new: str) -> bool:
    """True when the bump crosses a major version boundary."""
    try:
        return Version(new).major > Version(old).major
    except ValueError:
        return False
