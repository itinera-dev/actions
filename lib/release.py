"""Releases: the package version, the tag that requests a release, the tier claimed and the release notes."""

import json
import re
import tomllib
import urllib.parse

TIER_PATH = re.compile(r"cases/tier-(\d+)/")
HEADING = re.compile(r"##[ \t]+\[?v?(\d[^\]\s]*).*")
SECTION_END = re.compile(r"#{1,2}[ \t]|\[[^\]]+\]:\s")
PROPERTY_SPACE = " \t\f"
PROPERTY_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}
ESCAPE = re.compile(r"\\(u[0-9A-Fa-f]{0,4}|.)", re.DOTALL)
UNICODE_ESCAPE = re.compile(r"u[0-9A-Fa-f]{4}")
PROPERTY_LINE_END = re.compile(r"\r\n|\r|\n")


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


def gradle_properties_version(text):
    """The version a gradle.properties declares under the key `version`, or None."""
    return java_properties(text).get("version")


def java_properties(text):
    """The entries of a Java properties file, read as java.util.Properties reads one: blank lines and comments
    skipped, a line ending in an odd number of backslashes continued on the next, each key ending at its first
    unescaped "=", ":" or white space, and a later entry replacing an earlier one with the same key.

    Raises ValueError on a malformed Unicode escape.
    """
    entries = {}
    for line in logical_lines(text):
        key, value = split_entry(line)
        entries[unescape(key)] = unescape(value)
    return entries


def logical_lines(text):
    """The entries of a properties file, one string each, with continued lines joined. A line ends only at a line
    feed, a carriage return or both, and a continuation that leaves the entry empty starts it afresh, so the next
    line may still be blank or a comment."""
    pending = ""
    for natural in PROPERTY_LINE_END.split(text):
        line = natural.lstrip(PROPERTY_SPACE)
        if not pending and (not line or line[0] in "#!"):
            continue
        line = pending + line
        if continues(line):
            pending = line[:-1]
            continue
        pending = ""
        yield line
    if pending:
        yield pending


def continues(line):
    """Whether a properties line goes on in the next one: it ends in an odd number of backslashes."""
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def split_entry(line):
    """The key and the value of a properties entry, still escaped."""
    i = 0
    while i < len(line) and line[i] not in "=:" and line[i] not in PROPERTY_SPACE:
        i += 2 if line[i] == "\\" else 1
    key, rest = line[:i], line[i:].lstrip(PROPERTY_SPACE)
    if rest[:1] in ("=", ":"):
        rest = rest[1:].lstrip(PROPERTY_SPACE)
    return key, rest


def unescape(text):
    """A properties key or value without its escapes."""
    def replace(match):
        escaped = match.group(1)
        if escaped.startswith("u"):
            if not UNICODE_ESCAPE.fullmatch(escaped):
                raise ValueError(f'"\\{escaped}" is not a Unicode escape.')
            return chr(int(escaped[1:], 16))
        return PROPERTY_ESCAPES.get(escaped, escaped)

    return ESCAPE.sub(replace, text)


MANIFEST_READERS = {
    "Cargo.toml": cargo_version,
    "gradle.properties": gradle_properties_version,
    "package.json": package_json_version,
}


def manifest_encoding(name):
    """The encoding of the manifest called `name`: ISO 8859-1 for a gradle.properties, which Gradle reads as
    java.util.Properties reads a stream, and UTF-8 for the others."""
    return "latin-1" if name.rsplit("/", 1)[-1] == "gradle.properties" else "utf-8"


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


def tier_problems(scenarios, proposals, capabilities, claimed, manifest):
    """The proposals of tiers 1 to `claimed` missing from `proposals`, the list in the conformance manifest called
    `manifest`.

    A proposal is required only when one of its scenarios applies to the language, needing no capability that
    `capabilities` leaves unclaimed.
    """
    if claimed < 1:
        return [f"The tier claimed must be 1 or more, not {claimed}."]
    in_tiers = [s for s in scenarios if (t := tier(s)) is not None and t <= claimed]
    if not set().union(*(s.proposals() for s in in_tiers)):
        return [f"The cases hold no proposal of tiers 1 to {claimed}."]
    required = set().union(*(s.proposals() for s in in_tiers if s.applies(capabilities)))
    return [
        f"Proposal {n:04d}, of tier {claimed} or below, is not listed in {manifest}."
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
