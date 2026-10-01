"""After a merge, close and lock the issue of every proposal file the pull request added."""

import os

from lib.github_api import GitHub, GitHubError
from lib.proposals import proposal_numbers


def main():
    repo, pr = os.environ["REPO"], int(os.environ["PR"])
    github = GitHub(os.environ["GH_TOKEN"])

    added = [f["filename"] for f in github.get_all(f"/repos/{repo}/pulls/{pr}/files") if f["status"] == "added"]
    numbers = proposal_numbers(added)
    if not numbers:
        print("No proposal file added; nothing to do.")
        return

    for n in numbers:
        issue = github.get(f"/repos/{repo}/issues/{n}")
        if "proposal" not in {label["name"] for label in issue["labels"]}:
            print(f"#{n} is not labelled proposal; skipped.")
            continue
        if issue["state"] == "open":
            github.post(f"/repos/{repo}/issues/{n}/comments", {"body": f"Accepted in #{pr}."})
            github.patch(f"/repos/{repo}/issues/{n}", {"state": "closed", "state_reason": "completed"})
        if not issue["locked"]:
            try:
                github.put(f"/repos/{repo}/issues/{n}/lock", {"lock_reason": "resolved"})
            except GitHubError as error:
                print(f"::warning::Could not lock #{n}: {error}")
        print(f"#{n} closed and locked.")


if __name__ == "__main__":
    main()
