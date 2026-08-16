"""One-off fixes for mypy/B904 issues discovered during quality gates."""

import re

# --- cli.py ---
c = open("src/depdiff/cli.py").read()
c = c.replace("def _dep(d) -> dict[str, object] | None:",
              "def _dep(d: Dependency | None) -> dict[str, object] | None:")
c = c.replace("    head_label, head_content = str(source), file_at_head(repo, source)\n"
              "    if \":\" in source and not source.endswith(\":\"):\n"
              "        # ref:path only if the bare string is not a working-tree file\n"
              "        if head_content is None:\n"
              "            ref, _, file_path = source.partition(\":\")\n"
              "            return file_path, file_at_ref(repo, ref, file_path)\n"
              "    return head_label, head_content",
              "    head_label, head_content = str(source), file_at_head(repo, source)\n"
              "    if \":\" in source and not source.endswith(\":\") and head_content is None:\n"
              "        ref, _, file_path = source.partition(\":\")\n"
              "        return file_path, file_at_ref(repo, ref, file_path)\n"
              "    assert head_content is not None\n"
              "    return head_label, head_content")
open("src/depdiff/cli.py", "w").write(c)

# --- parsers.py ---
p = open("src/depdiff/parsers.py").read()
p = p.replace("def _make_req_line():\n", "def _make_req_line() -> re.Pattern[str]:\n")
p = p.replace("import tomli", "import tomli  # type: ignore[import-not-found]")
open("src/depdiff/parsers.py", "w").write(p)

# --- semver.py ---
s = open("src/depdiff/semver.py").read()
s = s.replace("class Version:\n    __slots__ = (\"raw\", \"numbers\", \"pre\", \"post\")",
              "class Version:\n    __slots__ = (\"raw\", \"numbers\", \"pre\", \"post\")\n\n    raw: str\n    numbers: tuple[int, ...]\n    pre: tuple[int, int] | None\n    post: int")
open("src/depdiff/semver.py", "w").write(s)

# --- engine.py ---
e = open("src/depdiff/engine.py").read()
e = e.replace("    try:\n        ov, nv = Version(old.version), Version(new.version)\n    except ValueError:\n        ov = nv = None",
              "    try:\n        ov, nv = Version(old.version), Version(new.version)\n    except ValueError:\n        ov, nv = None, None")
open("src/depdiff/engine.py", "w").write(e)

# --- git.py: B904 ---
g = open("src/depdiff/git.py").read()
g = g.replace("    except GitRefError:\n        raise GitRefError(f\"not a git repository (or any parent): {path!r}\")",
              "    except GitRefError as exc:\n        raise GitRefError(f\"not a git repository (or any parent): {path!r}\") from exc")
g = g.replace("    except GitRefError:\n        raise GitRefError(f\"cannot resolve ref {ref!r}\")",
              "    except GitRefError as exc:\n        raise GitRefError(f\"cannot resolve ref {ref!r}\") from exc")
g = g.replace("    except GitRefError:\n        raise GitRefError(f\"cannot read {file_path!r} at {ref!r}\")",
              "    except GitRefError as exc:\n        raise GitRefError(f\"cannot read {file_path!r} at {ref!r}\") from exc")
open("src/depdiff/git.py", "w").write(g)

# --- cli.py: B904 (main) ---
c = open("src/depdiff/cli.py").read()
c = c.replace("    except (GitRefError, DepDiffError) as exc:\n        print(f\"depdiff: {exc}\", file=sys.stderr)\n        return 3\n",
              "    except (GitRefError, DepDiffError) as exc:\n        raise GitRefError(f\"source read failed: {exc}\") from exc\n")
c = c.replace("    except (ParseError, UnsupportedFormatError) as exc:\n        print(f\"depdiff: old snapshot: {exc}\", file=sys.stderr)\n        return 3",
              "    except (ParseError, UnsupportedFormatError) as exc:\n        raise ParseError(f\"old snapshot: {exc}\") from exc")
c = c.replace("    except (ParseError, UnsupportedFormatError) as exc:\n        print(f\"depdiff: new snapshot: {exc}\", file=sys.stderr)\n        return 3",
              "    except (ParseError, UnsupportedFormatError) as exc:\n        raise ParseError(f\"new snapshot: {exc}\") from exc")
open("src/depdiff/cli.py", "w").write(c)
print("fixed")
