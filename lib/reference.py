"""API references in editions, as the book has them: the newest release at the root, a frozen copy of every release
under its version, and the main branch under next/."""

import pathlib
import re
import shutil

from lib.github_api import unpack

SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?"
)


def version_of_release(release):
    """The semantic version a release's tag names after "v", or None for a draft or any other tag."""
    tag = release.get("tag_name") or ""
    if release.get("draft") or not tag.startswith("v") or not SEMVER.fullmatch(tag[1:]):
        return None
    return tag[1:]


def identifier_key(identifier):
    """Orders a pre-release identifier as semantic versioning does: numbers by value, before any text."""
    return (0, int(identifier), "") if identifier.isdigit() else (1, 0, identifier)


def precedence(version):
    """A key ordering semantic versions by precedence, each pre-release before its release."""
    match = SEMVER.fullmatch(version)
    core = tuple(int(part) for part in match.group(1, 2, 3))
    pre = match.group(4)
    if pre is None:
        return (core, (1,))
    return (core, (0, *(identifier_key(identifier) for identifier in pre.split("."))))


def editions(releases, asset):
    """The editions the releases give, newest first, each a version and the id of its reference, and a warning for
    each release that names a version but has no reference attached."""
    found, warnings = [], []
    for release in releases:
        version = version_of_release(release)
        if version is None:
            continue
        attached = next((a for a in release.get("assets", []) if a.get("name") == asset), None)
        if attached is None:
            warnings.append(f"The release {release['tag_name']} has no {asset} attached, so it has no edition.")
            continue
        found.append({"version": version, "asset_id": attached["id"]})
    found.sort(key=lambda edition: precedence(edition["version"]), reverse=True)
    return found, warnings


def waiting_page():
    """The front page while nothing is released: it sends the reader to next/."""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta http-equiv="refresh" content="0; url=next/">\n<title>API reference</title>\n</head>\n<body>\n'
        '<p>No version is released yet. <a href="next/">The reference of the main branch</a> is under next/.</p>\n'
        "</body>\n</html>\n"
    )


def overlap(out, next_reference):
    """Why `out` cannot be emptied and filled beside `next_reference`, or None when it can: emptying it must not
    remove the working directory, nor the reference it is given, and the reference must not be copied into itself."""
    out, next_reference, here = (pathlib.Path(path).resolve() for path in (out, next_reference, "."))
    if out == here or out in here.parents:
        return f"{out} holds the working directory, which emptying it would remove."
    if out == next_reference or out in next_reference.parents:
        return f"{out} holds {next_reference}, which emptying it would remove."
    if next_reference in out.parents:
        return f"{out} lies inside {next_reference}, which would be copied into itself."
    return None


def build_site(out, next_reference, found, fetch):
    """Lays out the editions in `out`, emptied first, which `overlap` must have allowed: `next_reference` under
    next/, each release's reference, as `fetch(edition)` gives its archive, under its version, and the newest release
    again at the root."""
    out = pathlib.Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(next_reference, out / "next")
    for edition in found:
        (out / edition["version"]).mkdir()
        unpack(fetch(edition), out / edition["version"])
    if found:
        shutil.copytree(out / found[0]["version"], out, dirs_exist_ok=True)
    else:
        (out / "index.html").write_text(waiting_page(), encoding="utf-8")
