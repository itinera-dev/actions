"""Create the GitHub release of a pushed tag, with the changelog's notes and the report files attached."""

import mimetypes
import os
import pathlib
import sys
from typing import NoReturn

from lib.github_api import GitHub, GitHubError
from lib.release import asset_upload_url, changelog_section, draft_release, existing_release, version_of_tag


def fail(problems) -> NoReturn:
    print("The release was not created:")
    for problem in problems:
        print(f"::error::{problem}")
    sys.exit(1)


def discard_draft(github, repo, release):
    """Delete a draft release that could not be completed, saying what became of it."""
    try:
        github.delete(f"/repos/{repo}/releases/{release['id']}")
    except GitHubError as error:
        return f"The draft release could not be deleted, and a re-run deletes it: {error}"
    return "The draft release was deleted; the job can be re-run."


def main():
    env = os.environ
    repo, tag = env["REPO"], env["TAG"]
    github = GitHub(env["GH_TOKEN"])

    version = version_of_tag(tag)
    try:
        notes = changelog_section(pathlib.Path(env["CHANGELOG"]).read_text(encoding="utf-8"), version)
    except (OSError, ValueError) as error:
        fail([f"{env['CHANGELOG']} cannot be read: {error}"])
    if notes is None:
        fail([f"{env['CHANGELOG']} has no notes for {version}."])
    assets = sorted(p for p in pathlib.Path(env["ASSETS"]).glob("*") if p.is_file())
    if not assets:
        fail([f"{env['ASSETS']} holds no files to attach."])

    try:
        existing = existing_release(github.get_all(f"/repos/{repo}/releases"), tag)
        if existing is not None and not existing["draft"]:
            print(f"{tag} is already released: {existing['html_url']}")
            return
        if existing is not None:
            github.delete(f"/repos/{repo}/releases/{existing['id']}")
            print(f"Deleted the draft release left by an earlier run for {tag}.")
        release = github.post(f"/repos/{repo}/releases", draft_release(tag, notes))
    except GitHubError as error:
        fail([str(error)])
    try:
        for path in assets:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            github.upload(asset_upload_url(release, path.name), path.read_bytes(), content_type)
            print(f"Attached {path.name}.")
        published = github.patch(f"/repos/{repo}/releases/{release['id']}", {"draft": False})
    except GitHubError as error:
        fail([str(error), discard_draft(github, repo, release)])
    print(f"Released {tag}: {published['html_url']}")


if __name__ == "__main__":
    main()
