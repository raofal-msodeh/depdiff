"""Full test suite for DepDiff: parsers, semver, policy, engine, CLI, git sources."""

from __future__ import annotations

import json
import subprocess
import textwrap

import pytest

from depdiff.engine import diff_snapshots
from depdiff.errors import ParseError, UnsupportedFormatError
from depdiff.models import Change, ChangeKind, Dependency, RiskLevel, Snapshot
from depdiff.parsers import parse_lockfile
from depdiff.policy import classify_change, license_class
from depdiff.semver import Version, is_major_jump

# ---------------------------------------------------------------------------
# semver
# ---------------------------------------------------------------------------


class TestSemver:
    def test_basic_ordering(self) -> None:
        assert Version("1.0.0") < Version("1.0.1") < Version("1.1.0") < Version("2.0.0")

    def test_prerelease_below_release(self) -> None:
        assert Version("1.0.1-alpha.1") < Version("1.0.1")

    def test_prerelease_ordering(self) -> None:
        assert Version("1.0.0-alpha.1") < Version("1.0.0-beta.1") < Version("1.0.0-rc.1")

    def test_post_release_above_release(self) -> None:
        assert Version("1.0.0") < Version("1.0.0.post1")

    def test_dev_below_release(self) -> None:
        assert Version("1.0.0.dev4") < Version("1.0.0")

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            Version("not-a-version")

    def test_equality(self) -> None:
        assert Version("1.2.3") == Version("1.2.3")
        assert Version("1.2.3") != Version("1.2.4")

    def test_major_jump(self) -> None:
        assert is_major_jump("1.4.2", "2.0.0")
        assert not is_major_jump("1.4.2", "1.9.9")

    def test_major_jump_invalid(self) -> None:
        assert not is_major_jump("1.0", "garbage")


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------

NPM_LOCK = textwrap.dedent("""\
    {
      "name": "demo",
      "lockfileVersion": 3,
      "packages": {
        "": {"name": "demo"},
        "node_modules/express": {"version": "4.18.2", "license": "MIT"},
        "node_modules/foo/bar/node_modules/nested": {"version": "1.0.0", "license": "ISC"},
        "node_modules/no-version": {"license": "MIT"}
      }
    }
""")


class TestParsers:
    def test_npm_basic(self) -> None:
        snap = parse_lockfile(NPM_LOCK, "package-lock.json")
        assert snap.format == "npm-lock3"
        assert snap.dependencies["express"].version == "4.18.2"
        assert snap.dependencies["express"].license_ids == ("MIT",)
        # nested install prefers most specific segment
        assert snap.dependencies["nested"].version == "1.0.0"

    def test_npm_rejects_invalid_version(self) -> None:
        # every real package carries an unparsable version → nothing to diff
        data = json.loads(NPM_LOCK)
        data["packages"]["node_modules/express"]["version"] = "not-semver"
        data["packages"]["node_modules/no-version"]["version"] = "also-broken"
        data["packages"]["node_modules/foo/bar/node_modules/nested"]["version"] = "third-broken"
        with pytest.raises(ParseError):
            parse_lockfile(json.dumps(data), "package-lock.json")

    def test_npm_rejects_lockfile_v1(self) -> None:
        data = {"lockfileVersion": 1, "dependencies": {"x": {"version": "1.0.0"}}}
        with pytest.raises(UnsupportedFormatError):
            parse_lockfile(json.dumps(data), "package-lock.json")

    def test_poetry(self) -> None:
        lock = textwrap.dedent("""\
            [metadata]
            lock-version = "2.0"
            content-hash = "abc"

            [[package]]
            name = "requests"
            version = "2.31.0"
            optional = false
            python-versions = ">=3.7"
            files = []

            [[package]]
            name = "copyleft-lib"
            version = "0.2.0"
            optional = false
            python-versions = "*"
            license = "GPL-3.0-only"
            files = []
        """)
        snap = parse_lockfile(lock, "poetry.lock")
        assert snap.format == "poetry"
        assert snap.dependencies["requests"].version == "2.31.0"
        assert snap.dependencies["copyleft-lib"].license_ids == ("GPL-3.0-only",)

    def test_poetry_legacy_11(self) -> None:
        lock = textwrap.dedent("""\
            [metadata]
            content-hash = "xyz"

            [[package]]
            name = "legacy"
            version = "0.1.0"
            description = "d"
            category = "main"
            optional = false
            python-versions = "*"
        """)
        snap = parse_lockfile(lock, "poetry.lock")
        assert snap.dependencies["legacy"].version == "0.1.0"

    def test_cargo(self) -> None:
        lock = textwrap.dedent("""\
            version = 3

            [[package]]
            name = "serde"
            version = "1.0.190"

            [[package]]
            name = "tokio"
            version = "1.34.0"
            license = "MIT"
        """)
        snap = parse_lockfile(lock, "Cargo.lock")
        assert snap.format == "cargo"
        assert snap.dependencies["serde"].version == "1.0.190"
        assert snap.dependencies["tokio"].license_ids == ("MIT",)

    def test_requirements(self) -> None:
        req = textwrap.dedent("""\
            # pinned deps
            flask==3.0.0
            werkzeug==3.0.1  # inline comment
            numpy==1.26.2 \
                --hash=sha256:abc

            -e git+https://x.git#egg=y
        """)
        snap = parse_lockfile(req, "requirements.txt")
        assert snap.format == "requirements"
        assert snap.dependencies["flask"].version == "3.0.0"
        assert snap.dependencies["werkzeug"].version == "3.0.1"
        assert "y" not in snap.dependencies

    def test_requirements_rejects_unpinned(self) -> None:
        with pytest.raises(ParseError):
            parse_lockfile("flask>=3.0.0\n", "requirements.txt")

    def test_requirements_accepts_markers_and_extras(self) -> None:
        req = 'flask==3.0.0 ; python_version >= "3.9"\nrequests[security]==2.31.0\n'
        snap = parse_lockfile(req, "requirements.txt")
        assert snap.dependencies["flask"].version == "3.0.0"
        assert snap.dependencies["requests"].version == "2.31.0"

    def test_unknown_format_rejected(self) -> None:
        with pytest.raises(UnsupportedFormatError):
            parse_lockfile("this is not a lock file", "notes.md")

    def test_empty_file_rejected(self) -> None:
        with pytest.raises(ParseError):
            parse_lockfile("", "package-lock.json")

    def test_filename_detection(self) -> None:
        from depdiff.parsers import detect_filename

        assert detect_filename("package-lock.json")
        assert detect_filename("path/to/poetry.lock")
        assert detect_filename("requirements-dev.txt")
        assert detect_filename("Cargo.lock")
        assert not detect_filename("setup.cfg")


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

MIT = Dependency("x", "1.0.0", ("MIT",))
AGPL = Dependency("x", "1.0.0", ("AGPL-3.0-only",))
LGPL = Dependency("x", "1.0.0", ("LGPL-3.0-only",))
UNKN = Dependency("x", "1.0.0", ("WeirdLicense-1.0",))
NONE = Dependency("x", "1.0.0", ())


class TestPolicy:
    def test_license_classes(self) -> None:
        assert license_class(("MIT", "Apache-2.0")) == "permissive"
        assert license_class(("LGPL-2.1-only",)) == "weak"
        assert license_class(("GPL-3.0-only",)) == "strong"
        assert license_class(()) == "unknown"
        assert license_class(("Weird-1.0",)) == "unknown"

    def test_added_agpl_blocks(self) -> None:
        out = classify_change(Change(ChangeKind.ADDED, "a", new=AGPL))
        assert out.risk == RiskLevel.BLOCK

    def test_added_unknown_declared_format_blocks(self) -> None:
        out = classify_change(Change(ChangeKind.ADDED, "a", new=UNKN))
        assert out.risk == RiskLevel.BLOCK

    def test_added_no_license_format_warns(self) -> None:
        out = classify_change(Change(ChangeKind.ADDED, "a", new=NONE))
        assert out.risk == RiskLevel.WARN

    def test_added_lgpl_warns(self) -> None:
        out = classify_change(Change(ChangeKind.ADDED, "a", new=LGPL))
        assert out.risk == RiskLevel.WARN

    def test_added_mit_safe(self) -> None:
        out = classify_change(Change(ChangeKind.ADDED, "a", new=MIT))
        assert out.risk == RiskLevel.SAFE

    def test_removed_always_safe(self) -> None:
        out = classify_change(Change(ChangeKind.REMOVED, "a", old=AGPL))
        assert out.risk == RiskLevel.SAFE

    def test_upgraded_major_warns(self) -> None:
        out = classify_change(
            Change(
                ChangeKind.UPGRADED,
                "a",
                old=Dependency("a", "1.0.0", ("MIT",)),
                new=Dependency("a", "2.0.0", ("MIT",)),
            )
        )
        assert out.risk == RiskLevel.WARN
        assert "major" in out.reason

    def test_relicensed_permissive_to_unknown_blocks(self) -> None:
        out = classify_change(Change(ChangeKind.RELICENSED, "a", old=MIT, new=UNKN))
        assert out.risk == RiskLevel.BLOCK

    def test_relicensed_to_strong_blocks(self) -> None:
        out = classify_change(Change(ChangeKind.RELICENSED, "a", old=MIT, new=AGPL))
        assert out.risk == RiskLevel.BLOCK

    def test_downgrade_no_risk(self) -> None:
        out = classify_change(
            Change(
                ChangeKind.DOWNGRADED,
                "a",
                old=Dependency("a", "2.0.0", ("MIT",)),
                new=Dependency("a", "1.9.9", ("MIT",)),
            )
        )
        assert out.risk == RiskLevel.SAFE


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------


class TestEngine:
    def test_added_removed_upgraded(self) -> None:
        old = Snapshot("npm-lock3", {"a": Dependency("a", "1.0.0", ("MIT",))})
        new = Snapshot(
            "npm-lock3",
            {
                "a": Dependency("a", "1.1.0", ("MIT",)),
                "b": Dependency("b", "2.0.0", ("GPL-3.0-only",)),
            },
        )
        report = diff_snapshots(old, new, old_source="s1", new_source="s2")
        kinds = {c.name: c.kind for c in report.changes}
        assert kinds["a"] == ChangeKind.UPGRADED
        assert kinds["b"] == ChangeKind.ADDED
        assert report.blocked and report.blocked[0].name == "b"

    def test_no_changes_empty_report(self) -> None:
        dep = {"a": Dependency("a", "1.0.0", ("MIT",))}
        report = diff_snapshots(
            Snapshot("npm-lock3", dep), Snapshot("npm-lock3", dep), old_source="x", new_source="x"
        )
        assert report.changes == []

    def test_relicensed_same_version(self) -> None:
        old = Snapshot("poetry", {"a": Dependency("a", "1.0.0", ("MIT",))})
        new = Snapshot("poetry", {"a": Dependency("a", "1.0.0", ("AGPL-3.0-only",))})
        report = diff_snapshots(old, new, old_source="x", new_source="y")
        assert report.changes[0].kind == ChangeKind.RELICENSED
        assert report.changes[0].risk == RiskLevel.BLOCK


# ---------------------------------------------------------------------------
# CLI + git sources
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        )

    run("init", "-q", "-b", "main")
    run("config", "user.name", "T")
    run("config", "user.email", "t@x")
    run("commit", "--allow-empty", "-q", "-m", "initial")
    run("commit", "--allow-empty", "-q", "-m", "second")
    return repo


class TestCliGit:
    def test_non_repo_rejected(self) -> None:
        from depdiff.cli import main

        assert main(["/tmp", "a", "b"]) == 3

    def test_relative_repo_rejected(self) -> None:
        from depdiff.cli import main

        assert main(["relative/path", "a", "b"]) == 3

    def test_missing_file_at_ref(self, git_repo) -> None:
        from depdiff.cli import main

        # repo exists but the file is absent at the ref → graceful error
        assert main([str(git_repo), "HEAD:missing.lock", "HEAD:also-missing.lock"]) == 3

    def test_unsupported_filename(self, git_repo) -> None:
        from depdiff.cli import main

        lock = git_repo / "setup.cfg"
        lock.write_text("[metadata]\n")
        subprocess.run(["git", "-C", str(git_repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-q", "-m", "x"], check=True)
        assert main([str(git_repo), "HEAD:setup.cfg", "HEAD:setup.cfg"]) == 3

    def test_full_flow_json(self, git_repo) -> None:
        from depdiff.cli import main

        lock = git_repo / "package-lock.json"
        lock1 = json.dumps(
            {
                "name": "r",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "r"},
                    "node_modules/a": {"version": "1.0.0", "license": "MIT"},
                },
            }
        )
        lock2 = json.dumps(
            {
                "name": "r",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "r"},
                    "node_modules/a": {"version": "1.0.0", "license": "MIT"},
                    "node_modules/b": {"version": "0.1.0", "license": "AGPL-3.0-only"},
                },
            }
        )
        lock.write_text(lock1)
        subprocess.run(["git", "-C", str(git_repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-q", "-m", "base"], check=True)
        lock.unlink()
        lock.write_text(lock2)
        subprocess.run(["git", "-C", str(git_repo), "add", "-A"], check=True)
        r2 = subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-q", "-m", "add-b"],
            capture_output=True,
            text=True,
        )
        if r2.returncode != 0:
            raise AssertionError(f"second commit failed: {r2.stderr}")
        dbg = subprocess.run(
            ["git", "-C", str(git_repo), "log", "--oneline", "--all"],
            capture_output=True,
            text=True,
        )
        print("HISTORY:\n", dbg.stdout)
        out = tmp_path_main(git_repo)
        ret = main(
            [
                str(git_repo),
                "HEAD~1:package-lock.json",
                "HEAD:package-lock.json",
                "--format",
                "json",
                "-o",
                str(out / "report.json"),
            ]
        )  # noqa: E501
        assert ret == 2
        report = json.loads((out / "report.json").read_text())
        assert report["summary"]["added"] == 1
        assert report["summary"]["blocked"] == 1
        names = {c["name"] for c in report["changes"]}
        assert names == {"b"}


def tmp_path_main(git_repo):
    """Helper to reuse git_repo's parent tmp dir for outputs."""
    from pathlib import Path

    return Path(git_repo).parent
