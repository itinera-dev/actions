"""Release claims: the `releases` section of a conformance manifest, which lets a published release claim patches of
the specification, and how each claim is checked.

Each entry maps a release tag of the language to the conformance tags that release passes, such as
"v0.1.0-beta.7": ["v0.1.0", "v0.1.1"] (the specification's PROCESS.md, "Claiming a patch for a published release").
A claim is proven by building the library at the release tag with the conformance runner from main, and running
the cases at each listed tag.
"""

import json
import pathlib
import re
import shutil
from dataclasses import dataclass, field

from lib.github_api import GitHubError

RELEASE_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?")
PATCH_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
# The file of the conformance repository listing, by version, the corrections that have no cases.
CORRECTIONS_FILE = "corrections-without-cases.json"


def version_key(tag):
    """The order of a version tag: a pre-release, such as v0.1.0-rc.2, comes before its version. None when `tag` is
    not a version tag."""
    match = RELEASE_TAG.fullmatch(tag)
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    return int(major), int(minor), int(patch), 0 if pre else 1


def minor_of(tag):
    """The minor version of a version tag, as "0.1", or None when `tag` is not a version tag, such as a commit."""
    key = version_key(tag)
    return None if key is None else f"{key[0]}.{key[1]}"


def releases_of(manifest):
    """The `releases` section of a manifest, or an empty one when it has none."""
    return manifest.get("releases", {}) if isinstance(manifest, dict) else {}


def releases_problems(releases):
    """What is wrong with the shape of a `releases` section, before anything is downloaded."""
    if not isinstance(releases, dict):
        return ['"releases" must map each release tag to the conformance tags it passes.']
    found = []
    for release, tags in releases.items():
        if not RELEASE_TAG.fullmatch(release):
            found.append(
                f'"releases": "{release}" is not a release tag such as "v0.1.0"; a claim names tags, never commits.'
            )
        if not isinstance(tags, list) or not tags or not all(isinstance(t, str) for t in tags):
            found.append(f'"releases.{release}" must be a list of conformance tags, such as ["v0.1.0", "v0.1.1"].')
            continue
        for tag in tags:
            if not PATCH_TAG.fullmatch(tag):
                found.append(
                    f'"releases.{release}" lists "{tag}", which is not a version of the specification such as "v0.1.1";'
                    " a claim names tags, never commits or release candidates."
                )
        for tag in sorted({t for t in tags if tags.count(t) > 1}):
            found.append(f'"releases.{release}" lists "{tag}" more than once.')
    return found


def section_changed(before, after):
    """Whether a pull request changes the `releases` section, from the manifests before and after it."""
    return releases_of(before) != releases_of(after)


def minor_problems(release, release_cases, tags):
    """The listed tags outside the minor version the release claims, which is that of the cases its manifest pins at
    its tag."""
    claimed = minor_of(release_cases)
    if claimed is None:
        return [
            f'"releases.{release}": the release\'s manifest pins the cases at "{release_cases}", which is not a version'
            " tag, so the minor version it claims cannot be told."
        ]
    return [
        f'"releases.{release}" lists "{tag}", outside spec {claimed}, the minor version the release claims.'
        for tag in tags
        if minor_of(tag) != claimed
    ]


def corrections_problems(release, release_cases, tag, text):
    """The corrections without cases that keep `release` from claiming `tag`, read from the conformance repository's
    list at that tag, holding `text`, or None when it has none.

    Patches are cumulative, so a correction counts when its version is later than the cases the release pinned and
    no later than `tag`.
    """
    if text is None:
        return []
    try:
        listed = json.loads(text)
    except ValueError as error:
        return [f"{CORRECTIONS_FILE} at {tag} cannot be read: {error}"]
    if not isinstance(listed, dict) or not all(
        version_key(v) is not None and isinstance(d, list) and all(isinstance(n, int) for n in d)
        for v, d in listed.items()
    ):
        return [f"{CORRECTIONS_FILE} at {tag} must map each version, such as \"v0.1.2\", to a list of defect numbers."]
    pinned, claimed = version_key(release_cases), version_key(tag)
    found = []
    for version in sorted(listed, key=version_key):
        if listed[version] and pinned < version_key(version) <= claimed:
            defects = ", ".join(f"spec#{n}" for n in listed[version])
            found.append(
                f'"releases.{release}" lists "{tag}", but {version} holds corrections without cases ({defects}),'
                " which a release claims only with a new release."
            )
    return found


def library_paths(text):
    """The paths of the library, from the action's input: separated by spaces or new lines, relative to the root of
    the repository."""
    return [p.strip("/") for p in text.split()]


def library_path_problems(paths):
    if not paths:
        return ['"library" must name at least one path: the parts of the repository built from the release tag.']
    return [
        f'"library" names "{p}", which must be a path inside the repository.'
        for p in paths
        if p in ("", ".") or pathlib.PurePosixPath(p).is_absolute() or ".." in pathlib.PurePosixPath(p).parts
    ]


def combine(runner_root, release_root, paths, into):
    """The repository at main, `runner_root`, copied to `into`, with each of `paths` taken from the release,
    `release_root`, instead: so the library is the release's and the runner, with everything else, is main's.

    Returns the problems, such as a path the release does not have.
    """
    missing = [p for p in paths if not (release_root / p).exists()]
    if missing:
        return [f'The release has no "{p}", which "library" names.' for p in missing]
    shutil.copytree(runner_root, into, symlinks=True)
    for p in paths:
        target = into / p
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        source = release_root / p
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
    return []


@dataclass
class Entry:
    """One claim: a release and one conformance tag it claims, with what its check found."""

    release: str
    cases: str
    release_commit: str = ""
    cases_commit: str = ""
    passed: bool = False
    problems: list = field(default_factory=list)


def report_dir_of(entry):
    """Where an entry's report goes, under the report directory: one directory for each release and cases tag."""
    return f"{entry.release}/{entry.cases}"


def summary(language, manifest_name, runner_ref, runner_commit, entries, names):
    """The summary of a run, as written to claims.json: what the compatibility table reads beside each entry's
    report, which has the same files, and so the same format, as the report a release carries."""
    return {
        "language": language or None,
        "manifest": manifest_name,
        "runner": {"ref": runner_ref, "commit": runner_commit},
        "entries": [
            {
                "release": e.release,
                "release_commit": e.release_commit,
                "cases": e.cases,
                "cases_commit": e.cases_commit,
                "passed": e.passed,
                "problems": e.problems,
                "cucumber": f"{report_dir_of(e)}/{names.cucumber}",
                "exclusions": f"{report_dir_of(e)}/{names.exclusions}",
            }
            for e in entries
        ],
    }


def summary_markdown(language, runner_ref, runner_commit, entries):
    """The run's summary for the job's page."""
    title = f"Release claims ({language})" if language else "Release claims"
    lines = [f"## {title}", "", f"Runner: {runner_ref} at {runner_commit}.", ""]
    if not entries:
        lines.append("No release claims a patch.")
    for e in entries:
        result = "passes" if e.passed else "fails"
        lines.append(f"- {e.release} (at {e.release_commit[:12]}) {result} the cases at {e.cases}.")
        lines += [f"  - {p}" for p in e.problems]
    return "\n".join(lines) + "\n"


class GitHubSource:
    """What the check reads from GitHub: tags, files and repositories."""

    def __init__(self, github):
        self._github = github

    def tag_commit(self, repo, tag):
        """The commit tagged `tag` in `repo`, or None when there is no such tag."""
        try:
            target = self._github.get(f"/repos/{repo}/git/ref/tags/{tag}")["object"]
        except GitHubError as error:
            if "failed with 404" in str(error):
                return None
            raise
        while target["type"] == "tag":
            target = self._github.get(f"/repos/{repo}/git/tags/{target['sha']}")["object"]
        return target["sha"]

    def branch_commit(self, repo, branch):
        return self._github.get(f"/repos/{repo}/commits/{branch}")["sha"]

    def file_at(self, repo, ref, path):
        """The text of `path` in `repo` at `ref`, or None when it is not there."""
        try:
            raw = self._github.download(f"/repos/{repo}/contents/{path}?ref={ref}", "application/vnd.github.raw+json")
            return raw.decode()
        except GitHubError as error:
            if "failed with 404" in str(error):
                return None
            raise

    def extract(self, repo, ref, into):
        return self._github.extract_repository(repo, ref, into)
