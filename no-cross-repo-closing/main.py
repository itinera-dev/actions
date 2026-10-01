"""Fail when the description or a commit message closes another repository's issue."""

import os
import sys

from lib.closing import cross_repo_closings
from lib.github_api import GitHub


def main():
    repo, pr = os.environ["REPO"], int(os.environ["PR"])
    github = GitHub(os.environ["GH_TOKEN"])

    messages = [c["commit"]["message"] for c in github.get_all(f"/repos/{repo}/pulls/{pr}/commits")]
    found = cross_repo_closings("\n".join([os.environ.get("PR_BODY", ""), *messages]), repo)
    if found:
        print('Closing keywords must not point at another repository. Use "Refs owner/repo#N" instead:')
        for reference in found:
            print(f"::error::{reference}")
        sys.exit(1)
    print("No cross-repository closing keywords.")


if __name__ == "__main__":
    main()
