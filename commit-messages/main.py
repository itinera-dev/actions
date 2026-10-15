"""Fail unless every commit of the pull request keeps the commit message convention.

Run with a revision range, such as `origin/main..HEAD`, it checks those commits of the local repository instead,
so a message can be put right before it is pushed.
"""

import os
import subprocess
import sys
from typing import NoReturn

from lib.commits import is_merge, parse_log, problems
from lib.github_api import GitHub

# GitHub lists at most this many commits of a pull request.
LISTED_COMMITS = 250


def fail(message) -> NoReturn:
    print(f"::error::{message}")
    sys.exit(1)


def pull_request_commits():
    repo, pr = os.environ["REPO"], int(os.environ["PR"])
    commits = GitHub(os.environ["GH_TOKEN"]).get_all(f"/repos/{repo}/pulls/{pr}/commits")
    if len(commits) >= LISTED_COMMITS:
        print(f"::warning::GitHub lists only {LISTED_COMMITS} commits of a pull request; the rest are unchecked.")
    return commits


def local_commits(revisions):
    try:
        output = subprocess.run(
            ["git", "log", "--format=%H%x00%P%x00%B%x1e", revisions], capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError as error:
        fail(f"git log {revisions} failed: {error.stderr.strip()}")
    return parse_log(output)


def main():
    commits = local_commits(sys.argv[1]) if len(sys.argv) > 1 else pull_request_commits()
    commits = [c for c in commits if not is_merge(c)]
    found = [(c, problem) for c in commits for problem in problems(c["commit"]["message"])]
    if found:
        print("These commit messages break the convention; reword them before merging:")
        for commit, problem in found:
            print(f"::error::{commit['sha'][:7]}: {problem}")
        sys.exit(1)
    print(f"All {len(commits)} commits keep the convention.")


if __name__ == "__main__":
    main()
