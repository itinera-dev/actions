"""Releases: the package version, the tag that requests a release, the tier claimed and the release notes."""

import json
import re
import tomllib
import urllib.parse

TIER_PATH = re.compile(r"cases/tier-(\d+)/")
HEADING = re.compile(r"##[ \t]+\[?v?(\d[^\]\s]*).*")
SECTION_END = re.compile(r"#{1,2}[ \t]|\[[^\]]+\]:\s")


def cargo_version(text):
    """The version a Cargo.toml declares, from `[workspace.package]` or else `[package]`, or None."""
    manifest = tomllib.loads(text)
    for table in (manifest.get("workspace", {}).get("package", {}), manifest.get("package", {})):
        version = table.get("version")
        if isinstance(version, str):
            return version
    return None


def package_json_version(text):
    """The version a package.json declares, or None."""
    manifest = json.loads(text)
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) else None


MANIFEST_READERS = {"Cargo.toml": cargo_version, "package.json": package_json_version}


def manifest_version(name, text):
    """The version declared by the manifest called `name`, holding `text`.

    Raises ValueError when the format is not known or the manifest declares no version.
    """
    reader = MANIFEST_READERS.get(name.rsplit("/", 1)[-1])
    if reader is None:
        known = ", ".join(sorted(MANIFEST_READERS))
        raise ValueError(f"{name} is not a manifest the release gate can read; it reads {known}.")
    try:
        version = reader(text)
    except ValueError as error:
        raise ValueError(f"{name} cannot be parsed: {error}") from error
    if version is None:
        raise ValueError(f"{name} declares no version.")
    return version


def tag_problems(ref_type, tag, version):
    """Why `tag` cannot request the release of `version`."""
    if ref_type != "tag":
        return [f"A release is requested by pushing a tag, not a {ref_type or 'ref'} ({tag})."]
    if tag != f"v{version}":
        return [f'The tag {tag} does not match the package version {version}; it must be "v{version}".']
    return []


def compare_path(repo, sha, branch):
    """The GitHub comparison from a commit to a branch, whose status says whether the branch contains the commit."""
    return f"/repos/{repo}/compare/{sha}...{branch}?per_page=1"


def on_branch(compare_status):
    """Whether a commit is on a branch, given the status of GitHub's comparison from the commit to the branch."""
    return compare_status in ("ahead", "identical")


def tier(scenario):
    """The tier of a scenario, from its feature's folder `cases/tier-N/`, or None."""
    match = TIER_PATH.match(scenario.feature)
    return int(match.group(1)) if match else None


def tier_problems(scenarios, proposals, claimed):
    """The proposals of tiers 1 to `claimed` that `proposals` does not list."""
    if claimed < 1:
        return [f"The tier claimed must be 1 or more, not {claimed}."]
    required = set().union(*(s.proposals() for s in scenarios if (t := tier(s)) is not None and t <= claimed))
    if not required:
        return [f"The cases hold no proposal of tiers 1 to {claimed}."]
    return [
        f"Proposal {n:04d}, of tier {claimed} or below, is not listed in conformance.json."
        for n in sorted(required - set(proposals))
    ]


def is_prerelease(version):
    """Whether a version has a pre-release part, as in 0.1.0-rc.1."""
    return "-" in version.split("+", 1)[0]


def changelog_section(text, version):
    """The notes of the changelog's section for `version`, or None when it has no section or the section is empty.

    The section starts at a heading such as "## [0.1.0] - 2026-10-11" or "## 0.1.0", and ends at the next heading
    of level 1 or 2, or at the link definitions that close a changelog, such as "[0.1.0]: https://...".
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if heading_version(line) == version), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if SECTION_END.match(lines[i])), len(lines))
    return "\n".join(lines[start + 1:end]).strip() or None


def heading_version(line):
    """The version a second-level heading names, or None for any other line."""
    match = HEADING.fullmatch(line.rstrip())
    return match.group(1) if match else None


def version_of_tag(tag):
    """The version a release tag names, without its leading "v"."""
    return tag.removeprefix("v")


def draft_release(tag, notes):
    """The request creating the draft GitHub release of `tag`, a pre-release when its version has a pre-release part."""
    return {
        "tag_name": tag,
        "name": tag,
        "body": notes,
        "draft": True,
        "prerelease": is_prerelease(version_of_tag(tag)),
    }


def existing_release(releases, tag):
    """The release of `tag` among `releases`, published or draft, or None."""
    return next((r for r in releases if r["tag_name"] == tag), None)


def asset_upload_url(release, name):
    """Where an asset called `name` is uploaded, from the release's templated upload URL."""
    return release["upload_url"].split("{", 1)[0] + "?" + urllib.parse.urlencode({"name": name})
