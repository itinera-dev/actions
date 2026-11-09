"""What the compatibility table reads from GitHub: releases, files at a tag, release assets and the cases."""

import pathlib
import tarfile
import tempfile
import urllib.parse

from lib.compatibility import TableError, proposal_title
from lib.conformance import read_scenarios
from lib.github_api import GitHubError


def decoded(data, what):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TableError(f"{what} is not UTF-8 text: {error}") from error


def ref(tag):
    return urllib.parse.quote(tag, safe="")


class Source:
    """What the table reads, from GitHub: each cases tag and the spec are downloaded once, and a tag that cannot be
    downloaded is tried only once."""

    def __init__(self, github, conformance, work):
        self._github = github
        self._conformance = conformance
        self._work = pathlib.Path(work)
        self._scenarios = {}

    def releases(self, repository):
        return self._github.get_all(f"/repos/{repository}/releases")

    def files(self, repository, tag):
        try:
            return {entry["name"] for entry in self._github.get(f"/repos/{repository}/contents?ref={ref(tag)}")}
        except GitHubError as error:
            raise TableError(f"The files of {repository} at {tag} cannot be read: {error}") from error

    def text(self, repository, path, tag):
        try:
            data = self._github.download(
                f"/repos/{repository}/contents/{urllib.parse.quote(path)}?ref={ref(tag)}", "application/vnd.github.raw"
            )
        except GitHubError as error:
            raise TableError(f"{path} cannot be read at {tag}: {error}") from error
        return decoded(data, path)

    def asset(self, repository, asset):
        try:
            data = self._github.download_asset(repository, asset["id"])
        except GitHubError as error:
            raise TableError(f"{asset['name']} cannot be downloaded: {error}") from error
        return decoded(data, asset["name"])

    def scenarios(self, cases):
        if cases not in self._scenarios:
            into = tempfile.mkdtemp(prefix="cases-", dir=self._work)
            try:
                root = self._github.extract_repository(self._conformance, ref(cases), into)
                self._scenarios[cases] = read_scenarios(root)
            except (GitHubError, OSError, ValueError, tarfile.TarError) as error:
                self._scenarios[cases] = TableError(
                    f"The cases at {self._conformance}@{cases} cannot be downloaded: {error}"
                )
        found = self._scenarios[cases]
        if isinstance(found, TableError):
            raise found
        return found

    def titles(self, spec):
        """The title and path of every proposal of the specification's main branch."""
        root = self._github.extract_repository(spec, "main", tempfile.mkdtemp(prefix="spec-", dir=self._work))
        return {
            path.name[:4]: {"title": proposal_title(path.read_text(encoding="utf-8")), "path": f"proposals/{path.name}"}
            for path in sorted(root.joinpath("proposals").glob("[0-9][0-9][0-9][0-9]-*.md"))
        }
